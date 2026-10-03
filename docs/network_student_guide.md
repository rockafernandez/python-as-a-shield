# Grupo Network — Taller de corrección automática con Python

Para los estudiantes `user01`–`user10` de la cuenta **network**. Sigue únicamente la guía de tu grupo.

## 1. Inicia sesión e identifica tus recursos

1. Usa únicamente la URL de inicio de sesión, el usuario y la contraseña temporal que te entregue el instructor.
2. Cambia la contraseña cuando se solicite. Selecciona **US East (N. Virginia), us-east-1**.
3. Confirma que estás en la cuenta asignada. Trabajarás desde la consola; no necesitas perfiles de CLI, claves de acceso ni CloudShell.
4. Sustituye `user01` por tu usuario y `01` por tu número de participante de dos dígitos en toda la guía.
5. Incluye estas etiquetas **en la solicitud de creación de cada recurso**, antes de confirmar:

```text
Workshop = true
Owner = user01
```

Los nombres y las etiquetas distinguen mayúsculas de minúsculas. Usa solamente tus recursos. No modifiques tu usuario de inicio de sesión, los roles existentes, las políticas, los límites de permisos, CloudTrail ni la configuración de la cuenta.

## 2. Crea tu función Lambda

1. Abre **Lambda → Functions → Create function → Author from scratch**.
2. Usa exactamente el nombre `user01-Remediator`. En **Runtime**, selecciona **Python 3.14** (`python3.14`).
3. Expande **Change default execution role** y selecciona **Use an existing role → user01-LambdaRole**. No crees un rol nuevo.
4. Agrega `Workshop=true` y `Owner=user01` en las opciones de creación. Crea la función. Si la consola no permite enviar las etiquetas requeridas al crearla, pide ayuda al instructor.
5. En **Configuration → General configuration**, comienza con **128 MB** y un tiempo máximo de ejecución de **10 segundos**. Deja la función fuera de una VPC.
6. Pega el código de tu grupo en `lambda_function.py`. Sustituye los valores indicados. Conserva el controlador `lambda_function.lambda_handler`. Pulsa **Deploy** después de cada cambio.
7. No cambies la configuración de concurrencia. Las solicitudes de aumento de cuota de las cuentas Network y Storage están pendientes; el instructor configurará las reservas si se aprueban.

El rol de ejecución permite aplicar las correcciones. El rol separado `user01-EventRole` permite que EventBridge invoque la función. Lambda obtiene credenciales temporales automáticamente; nunca pegues credenciales de AWS en el código.

El código es un ejemplo educativo alineado con los permisos del taller. No se ha probado en tus cuentas de AWS. Prueba primero un caso. Corrige una configuración concreta del laboratorio; no evalúa todas las posibles configuraciones inseguras de producción.

## 3. Crea tu grupo de seguridad y tu subred

El instructor proporciona el ID de la cuenta Network, el ID de la VPC del taller y el CIDR aprobado. La VPC ya existe; los estudiantes crean el grupo de seguridad y la subred.

1. Abre **VPC → Security groups → Create security group**. Usa `user01-SG`, agrega una descripción, selecciona la VPC del taller e incluye ambas etiquetas requeridas. Deja vacías las reglas de entrada y conserva las reglas de salida predeterminadas.
2. Anota el ID `sg-...`. No agregues etiquetas a reglas individuales; no tienes ese permiso.
3. Abre **VPC → Subnets → Create subnet**. Selecciona la VPC del taller, una zona de disponibilidad aprobada y tu CIDR asignado. Usa `user01-Subnet` e incluye ambas etiquetas. Crea una sola subred por solicitud.
4. Anota el ID `subnet-...`. Deja deshabilitada inicialmente la asignación automática de IPv4 pública.

Estos son los CIDR del ejemplo predeterminado. **La configuración real del instructor tiene prioridad.** No uses el rango de otro estudiante.

| Estudiante | CIDR de ejemplo |
|---|---|
| user01 | 10.90.1.0/24 |
| user02 | 10.90.2.0/24 |
| user03 | 10.90.3.0/24 |
| user04 | 10.90.4.0/24 |
| user05 | 10.90.5.0/24 |
| user06 | 10.90.6.0/24 |
| user07 | 10.90.7.0/24 |
| user08 | 10.90.8.0/24 |
| user09 | 10.90.9.0/24 |
| user10 | 10.90.10.0/24 |

No crees instancias, internet gateways, rutas ni NAT gateways. El laboratorio modifica configuraciones sin conectar servidores.

## 4. Implementa el código de corrección de tu grupo

Configura `OWNER`, `ACCOUNT_ID` y `VPC_ID` al inicio. Los tres casos del grupo de seguridad comparten una rama porque producen el mismo evento de API. El código elimina reglas de entrada IPv4 públicas para rangos TCP que incluyen SSH/RDP y reglas públicas de todos los protocolos. Conserva las reglas no relacionadas. El acceso público por IPv6 y otros servicios están fuera de estos ejercicios.

```python
import json
import boto3

OWNER = "user01"
ACCOUNT_ID = "REPLACE_NETWORK_ACCOUNT_ID"
VPC_ID = "REPLACE_WORKSHOP_VPC_ID"
ec2 = boto3.client("ec2", region_name="us-east-1")


def owned(resource):
    tags = {t["Key"]: t["Value"] for t in resource.get("Tags", [])}
    return (resource.get("VpcId") == VPC_ID
            and tags.get("Workshop") == "true" and tags.get("Owner") == OWNER)


def lambda_handler(event, context):
    d = event.get("detail", {})
    caller = f"arn:aws:iam::{ACCOUNT_ID}:user/workshop/{OWNER}"
    if (event.get("account") != ACCOUNT_ID or event.get("region") != "us-east-1"
            or d.get("eventSource") != "ec2.amazonaws.com"
            or d.get("userIdentity", {}).get("arn") != caller or "errorCode" in d):
        return {"outcome": "out_of_scope"}
    p = d.get("requestParameters") or {}
    name = d.get("eventName")
    if name == "AuthorizeSecurityGroupIngress":
        resource_id = p.get("groupId")
        if not resource_id:
            return {"outcome": "missing_group_id"}
        sg = ec2.describe_security_groups(GroupIds=[resource_id])["SecurityGroups"][0]
        if not owned(sg):
            return {"outcome": "out_of_scope"}
        removed = 0
        pager = ec2.get_paginator("describe_security_group_rules")
        for page in pager.paginate(Filters=[{"Name": "group-id", "Values": [resource_id]}]):
            for rule in page["SecurityGroupRules"]:
                if rule["IsEgress"] or rule.get("CidrIpv4") != "0.0.0.0/0":
                    continue
                risky = rule["IpProtocol"] == "-1" or (
                    rule["IpProtocol"] in ("tcp", "6") and any(
                        rule.get("FromPort", -1) <= port <= rule.get("ToPort", -1)
                        for port in (22, 3389)))
                if risky:
                    ec2.revoke_security_group_ingress(
                        GroupId=resource_id, SecurityGroupRuleIds=[rule["SecurityGroupRuleId"]])
                    removed += 1
        outcome = f"removed_{removed}_rules" if removed else "already_compliant"
    elif name == "ModifySubnetAttribute":
        resource_id = p.get("subnetId")
        if not resource_id:
            return {"outcome": "missing_subnet_id"}
        subnet = ec2.describe_subnets(SubnetIds=[resource_id])["Subnets"][0]
        if not owned(subnet):
            return {"outcome": "out_of_scope"}
        if subnet["MapPublicIpOnLaunch"]:
            ec2.modify_subnet_attribute(SubnetId=resource_id,
                                       MapPublicIpOnLaunch={"Value": False})
            outcome = "repair_requested"
        else:
            outcome = "already_compliant"
    else:
        return {"outcome": "unsupported_event"}
    result = {"event_id": event.get("id"), "resource": resource_id, "outcome": outcome}
    print(json.dumps(result))
    return result
```

## 5. Conecta EventBridge con tu función

1. Abre **Amazon EventBridge → Rules → Create rule**. Usa el bus **default** y una regla basada en un patrón de eventos, no una programación.
2. Usa el prefijo de tu usuario en el nombre indicado abajo. Si es necesario, utiliza Advanced Builder o el editor de patrones JSON personalizados.
3. Pega el patrón y sustituye `ACCOUNT_ID` y `user01`. En Storage, sustituye también `S3_BPA_EVENT` por el nombre del evento observado por el instructor.
4. Selecciona el destino **AWS service → Lambda function → user01-Remediator**.
5. En los permisos del destino, selecciona **Use existing role → user01-EventRole**. Envía el **evento completo**, sin transformar la entrada.
6. Si el asistente propone crear un rol o agregar una política de recursos a Lambda, selecciona el rol existente. Si esa opción no aparece, consulta al instructor; no solicites permisos más amplios.
7. Agrega las etiquetas Workshop/Owner requeridas si el formulario de creación de la regla lo permite. Revisa y habilita la regla.

El filtro del usuario que realiza la llamada excluye las correcciones hechas por el rol de Lambda y ayuda a evitar ciclos. El filtro `errorCode` ignora llamadas fallidas. El controlador vuelve a comprobar el alcance y el estado actual porque los eventos pueden duplicarse o llegar con retraso.
Crea la regla **`user01-Network`**. Una sola regla puede enviar los eventos de API del grupo a la misma función.

```json
{
  "source": [
    "aws.ec2"
  ],
  "detail-type": [
    "AWS API Call via CloudTrail"
  ],
  "account": [
    "ACCOUNT_ID"
  ],
  "region": [
    "us-east-1"
  ],
  "detail": {
    "eventSource": [
      "ec2.amazonaws.com"
    ],
    "eventName": [
      "AuthorizeSecurityGroupIngress",
      "ModifySubnetAttribute"
    ],
    "errorCode": [
      {
        "exists": false
      }
    ],
    "userIdentity": {
      "arn": [
        "arn:aws:iam::ACCOUNT_ID:user/workshop/user01"
      ]
    }
  }
}
```

## 6. Realiza los ejercicios, uno a la vez


### Ejercicio 1 — SSH público

1. Selecciona tu grupo de seguridad → **Inbound rules → Edit inbound rules → Add rule**.
2. Elige SSH/TCP, puerto **22**, origen IPv4 **0.0.0.0/0**. Guarda sin etiquetas en la regla.
3. Actualiza la vista: la regla SSH pública debe desaparecer. Si era la única regla insegura, espera `removed_1_rules`.

### Ejercicio 2 — RDP público

1. Agrega TCP, puerto **3389**, origen **0.0.0.0/0**, al mismo grupo.
2. Guarda y confirma que la regla se elimina.

### Ejercicio 3 — Entrada pública de todos los protocolos

1. Agrega **All traffic**, origen **0.0.0.0/0**.
2. Guarda y confirma que se elimina esa regla. No asocies el grupo a una carga de trabajo.

### Ejercicio 4 — IPv4 pública automática en la subred

1. Selecciona tu subred → **Actions → Edit subnet settings**.
2. Habilita **auto-assign public IPv4 address** y guarda.
3. Actualiza y confirma que queda deshabilitado. Cambia el valor predeterminado de la subred; no crea una instancia ni una IP pública facturable.

## 7. Verifica y registra la evidencia

Para **cada** ejercicio:

1. Actualiza la configuración del recurso hasta observar el estado esperado. La entrega del evento y la propagación de atributos son asíncronas; la corrección puede tardar.
2. Abre **Monitor → View CloudWatch logs** en tu función, o el grupo `/aws/lambda/user01-Remediator` precreado en CloudWatch. Busca el identificador del evento, el recurso y el resultado.
3. Guarda una captura del estado corregido y una entrada de registro sin datos sensibles. No incluyas contraseñas, secretos de claves de acceso ni eventos completos de IAM.
4. Con el evento de EventBridge sin datos sensibles proporcionado por el instructor, abre **Lambda → Test → Create new event**. Conserva la estructura completa del evento y los valores de tu usuario y recurso. Invócalo otra vez después de la corrección: debe devolver `already_compliant` sin nuevas modificaciones.
5. Registra el nombre del evento, el identificador del recurso, el resultado de la corrección y el resultado de repetir el evento sin cambios.

El resultado `repair_requested` en el registro no confirma que la corrección terminó: verifica también el estado del recurso. Si no aparecen registros, revisa la regla habilitada, el ARN exacto del usuario que hizo la llamada, la cuenta, la región, el destino y el rol existente de EventBridge. Pide al instructor que confirme que CloudTrail está registrando eventos de administración. Los estudiantes no necesitan configurar un trail ni inspeccionar todos los eventos de la cuenta.

Si aparece `AccessDenied`, revisa los nombres asignados, las etiquetas de creación y el rol seleccionado. No retires un límite de permisos ni flexibilices una SCP. Si la función informa que faltan campos, comparte con el instructor un evento sin datos sensibles para revisar su estructura real.

Con concurrencia compartida puede haber demoras si muchos estudiantes prueban al mismo tiempo. Provoca un cambio, verifica el resultado y después continúa. Si las demoras persisten, pide al instructor que revise **Errors, Throttles y Duration**.
## 8. Finaliza y limpia los recursos

1. Deshabilita primero tus reglas de EventBridge y mantenlas deshabilitadas durante la limpieza.
2. Guarda la evidencia y el código. Si una corrección falló, restaura manualmente la configuración segura.
3. Elimina únicamente los recursos de ejercicios que tus permisos permitan, según las indicaciones del grupo.
4. Notifica al instructor. Él elimina las funciones, los grupos de registros, los usuarios de prueba protegidos, las identidades de participantes, los roles y las políticas. Los estudiantes no pueden eliminar y volver a crear sus funciones Lambda.

Después de deshabilitar la regla, elimina tu subred vacía y tu grupo de seguridad sin uso. Conserva la VPC del taller.
## Referencias

- https://docs.aws.amazon.com/vpc/latest/userguide/create-subnets.html
- https://docs.aws.amazon.com/boto3/latest/reference/services/ec2/client/revoke_security_group_ingress.html
- https://docs.aws.amazon.com/boto3/latest/reference/services/ec2/client/modify_subnet_attribute.html
