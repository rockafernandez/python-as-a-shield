# Grupo Identity — Taller de corrección automática con Python

Para los estudiantes `user01`–`user10` de la cuenta **identity**. Sigue únicamente la guía de tu grupo.

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

## 3. Crea tu usuario de prueba de IAM sin permisos efectivos

Tu usuario de inicio de sesión es `user01`; el objetivo del ejercicio es **otro usuario**, `Workshop-Target-01`. Nunca apliques las políticas del ejercicio a tu usuario de inicio de sesión.

1. Abre **IAM → Users → Create user**. Ingresa `Workshop-Target-01` y sustituye `01` por tu número de participante.
2. Deja sin marcar **Provide user access to the AWS Management Console**.
3. Elige adjuntar políticas directamente, pero no selecciones políticas de permisos inicialmente.
4. Selecciona el límite de permisos existente **Workshop-Target-DenyAll**.
5. Incluye `Workshop=true` y `Owner=user01` antes de crear el usuario. Usa la ruta raíz `/`.
6. Revisa y crea el usuario. Confirma que el límite que deniega todas las acciones sigue adjunto.

Si la consola solo permite agregar las etiquetas o el límite después de crear el usuario, pide ayuda al instructor. Deben incluirse en la solicitud CreateUser. No crees un rol, un grupo ni un límite nuevo.

El límite que deniega todas las acciones impide que las políticas y claves del usuario de prueba autoricen acciones de AWS. Tu usuario de participante conserva sus propios permisos restringidos del taller.

## 4. Implementa el código de corrección de tu grupo

Configura `OWNER`, `NUMBER` y `ACCOUNT_ID`. Conserva el nombre de política en línea **WorkshopWildcardExercise**. El código verifica las etiquetas y el límite exacto, y modifica únicamente tu usuario de prueba y la política o clave del ejercicio. Conserva las demás políticas en línea. Reconoce el ejemplo con comodines literales; no evalúa todas las políticas posibles con permisos excesivos.

```python
# Serializa los resultados en JSON para facilitar su lectura en CloudWatch Logs.
import json
# Permite decodificar documentos de política si IAM los entrega como texto URL-encoded.
from urllib.parse import unquote
# Boto3 permite llamar a las API de AWS con las credenciales temporales del rol de Lambda.
import boto3

# Configuración del participante: sustituye estos valores por los de tu cuenta y usuario.
# Los nombres exactos delimitan los recursos que esta función puede corregir.
OWNER = "user01"
NUMBER = "01"
ACCOUNT_ID = "REPLACE_IDENTITY_ACCOUNT_ID"
TARGET = f"Workshop-Target-{NUMBER}"
INLINE_POLICY = "WorkshopWildcardExercise"
ADMIN = "arn:aws:iam::aws:policy/AdministratorAccess"
# IAM es un servicio global; el evento del taller se valida en us-east-1.
# El cliente usa el rol de ejecución y no las credenciales del usuario de prueba.
iam = boto3.client("iam")


# Punto de entrada de Lambda. EventBridge entrega el evento completo en event;
# context contiene información de la ejecución y no se necesita en este ejemplo.
def lambda_handler(event, context):
    # El sobre de EventBridge contiene cuenta, región e identificador del evento.
    # detail contiene la llamada registrada por CloudTrail: servicio, usuario y parámetros.
    d = event.get("detail", {})
    # userName identifica el objetivo; policyArn, policyName o responseElements
    # se usan después según el caso. El objetivo es distinto del usuario de inicio de sesión.
    p = d.get("requestParameters") or {}
    # Construye el ARN del participante que debe haber provocado el cambio.
    # Las llamadas del rol de esta Lambda quedan fuera de alcance, evitando ciclos.
    caller = f"arn:aws:iam::{ACCOUNT_ID}:user/workshop/{OWNER}"
    # Rechaza eventos de otra cuenta, región o identidad y llamadas que fallaron.
    # Esta validación se repite aquí aunque la regla de EventBridge también filtre eventos.
    if (event.get("account") != ACCOUNT_ID or event.get("region") != "us-east-1"
            or d.get("eventSource") != "iam.amazonaws.com"
            or d.get("userIdentity", {}).get("arn") != caller
            or "errorCode" in d or p.get("userName") != TARGET):
        return {"outcome": "out_of_scope"}
    # Consulta el usuario real y verifica etiquetas y ARN del límite obligatorio.
    # El límite de denegación total mantiene al objetivo sin permisos efectivos,
    # incluso mientras tiene AdministratorAccess, una política amplia o una clave activa.
    user = iam.get_user(UserName=TARGET)["User"]
    tags = {t["Key"]: t["Value"] for t in iam.list_user_tags(UserName=TARGET)["Tags"]}
    boundary = f"arn:aws:iam::{ACCOUNT_ID}:policy/workshop/Workshop-Target-DenyAll"
    if (tags.get("Workshop") != "true" or tags.get("Owner") != OWNER
            or user.get("PermissionsBoundary", {}).get("PermissionsBoundaryArn") != boundary):
        # Detiene la ejecución si la identidad no cumple las protecciones del taller.
        # No intenta corregir un objetivo cuya pertenencia o límite son distintos.
        raise ValueError("Target ownership or deny-all boundary mismatch")
    # Selecciona la corrección por eventName; por defecto el objetivo ya cumple.
    name = d.get("eventName")
    outcome = "already_compliant"
    # Caso 1: retirar exclusivamente AdministratorAccess del usuario de prueba.
    if name == "AttachUserPolicy":
        if p.get("policyArn") != ADMIN:
            return {"outcome": "out_of_scope"}
        # Lista todas las páginas de políticas adjuntas para comprobar el estado actual.
        policies = []
        for page in iam.get_paginator("list_attached_user_policies").paginate(UserName=TARGET):
            policies.extend(page["AttachedPolicies"])
        # Desvincula la política si sigue presente; no elimina la política administrada
        # ni modifica el límite del objetivo. Si ya fue retirada, no realiza cambios.
        if any(x["PolicyArn"] == ADMIN for x in policies):
            iam.detach_user_policy(UserName=TARGET, PolicyArn=ADMIN)
            outcome = "admin_policy_detached"
    # Caso 2: revisar únicamente la política en línea con el nombre del ejercicio.
    elif name == "PutUserPolicy":
        if p.get("policyName") != INLINE_POLICY:
            return {"outcome": "out_of_scope"}
        # Lee la política actual. Si otra invocación ya la eliminó, continúa con un
        # documento vacío para que repetir el evento no provoque un error por ausencia.
        try:
            doc = iam.get_user_policy(UserName=TARGET, PolicyName=INLINE_POLICY)["PolicyDocument"]
        except iam.exceptions.NoSuchEntityException:
            doc = {}
        # Boto3 suele devolver un diccionario; también se admite texto codificado.
        if isinstance(doc, str):
            doc = json.loads(unquote(doc))
        # Normaliza una instrucción única a una lista para recorrer ambas formas de JSON.
        statements = doc.get("Statement", [])
        if isinstance(statements, dict):
            statements = [statements]
        # Detecta el comodín literal *, como texto o como elemento de una lista.
        # No analiza patrones parciales ni calcula los permisos efectivos de toda la política.
        def wildcard(value):
            return value == "*" or isinstance(value, list) and "*" in value
        # Si una misma instrucción Allow tiene Action=* y Resource=*, elimina toda
        # la política en línea del ejercicio. Las demás políticas en línea se conservan.
        if any(s.get("Effect") == "Allow" and wildcard(s.get("Action"))
               and wildcard(s.get("Resource")) for s in statements):
            iam.delete_user_policy(UserName=TARGET, PolicyName=INLINE_POLICY)
            outcome = "exercise_policy_deleted"
    # Caso 3: desactivar solamente la clave nueva identificada por este evento.
    elif name == "CreateAccessKey":
        # El ID proviene de la respuesta de CreateAccessKey, no de los parámetros.
        # No se extrae, utiliza ni registra el secreto de la clave.
        key_id = ((d.get("responseElements") or {}).get("accessKey") or {}).get("accessKeyId")
        if not key_id:
            return {"outcome": "missing_key_id"}
        # Consulta el estado actual de las claves del objetivo para evitar actualizar
        # una clave que ya fue eliminada o desactivada por otra invocación.
        keys = iam.list_access_keys(UserName=TARGET)["AccessKeyMetadata"]
        if any(k["AccessKeyId"] == key_id and k["Status"] == "Active" for k in keys):
            # Marca la clave como Inactive. No elimina otras claves ni cambia el login
            # del participante; el objetivo de prueba no tiene acceso a la consola.
            iam.update_access_key(UserName=TARGET, AccessKeyId=key_id, Status="Inactive")
            outcome = "key_deactivated"
    else:
        # No modifica el usuario ante eventos distintos de los tres casos del taller.
        return {"outcome": "unsupported_event"}
    # Registra únicamente el identificador, el recurso y el resultado de la corrección.
    # No imprime el evento completo ni credenciales. Devuelve el mismo resumen al invocador.
    result = {"event_id": event.get("id"), "resource": TARGET, "outcome": outcome}
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
Crea la regla **`user01-Identity`**. Una sola regla puede enviar los eventos de API del grupo a la misma función.

```json
{
  "source": [
    "aws.iam"
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
      "iam.amazonaws.com"
    ],
    "eventName": [
      "AttachUserPolicy",
      "PutUserPolicy",
      "CreateAccessKey"
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


### Ejercicio 5 — Adjuntar AdministratorAccess

1. Abre tu **usuario de prueba** → Permissions → Add permissions → Attach policies directly.
2. Selecciona **AdministratorAccess** y adjúntala. Conserva el límite que deniega todas las acciones.
3. Actualiza: AdministratorAccess debe retirarse automáticamente. El límite permanece.

### Ejercicio 6 — Política en línea con comodines

1. En tu usuario de prueba, crea una política en línea con el editor JSON:

```json
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"*","Resource":"*"}]}
```

2. Usa exactamente el nombre **WorkshopWildcardExercise** y guarda.
3. Actualiza: esa política debe desaparecer. El código elimina toda la política de ese nombre; no agregues instrucciones ajenas al ejercicio.

### Ejercicio 7 — Crear una clave de acceso

1. Abre tu usuario de prueba → **Security credentials → Create access key**. Selecciona la opción adecuada para el caso de prueba y confirma el aviso si se solicita.
2. Crea la clave. No descargues, copies, uses ni distribuyas su secreto.
3. Regresa a la lista de claves del usuario de prueba. Confirma que la nueva clave queda **Inactive**.
4. Elimina la clave inactiva después de registrar la evidencia. IAM permite como máximo dos claves por usuario; no las acumules.

La clave pertenece al usuario de prueba sin permisos efectivos, no a tu usuario de inicio de sesión. El código obtiene el ID de la nueva clave del evento y desactiva únicamente esa clave.

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

Después de deshabilitar la regla, elimina tus claves de prueba y las políticas del ejercicio que permanezcan. No retires el límite. Pide al instructor que elimine el usuario de prueba; los estudiantes no tienen permiso para eliminarlo.
## Referencias

- https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html
- https://docs.aws.amazon.com/IAM/latest/APIReference/API_CreateUser.html
- https://docs.aws.amazon.com/boto3/latest/reference/services/iam/client/update_access_key.html
