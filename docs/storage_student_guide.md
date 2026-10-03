# Grupo Storage — Taller de corrección automática con Python

Para los estudiantes `user01`–`user10` de la cuenta **storage**. Sigue únicamente la guía de tu grupo.

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

## 3. Crea tu bucket y tu cola vacíos

Pide al instructor el ID de la cuenta Storage. El evento de CloudTrail para actualizar Block Public Access del bucket es **`PutBucketPublicAccessBlock`** y ya está configurado en el código y la regla. El nombre del evento de CloudTrail difiere del nombre de la operación de Boto3 (`put_public_access_block`).

1. Abre **S3 → Create bucket**. Selecciona un bucket de uso general en us-east-1.
2. Usa exactamente `workshop-ACCOUNT_ID-student-01-pythonshield`; sustituye el ID de la cuenta Storage y tu número de dos dígitos.
3. Agrega ambas etiquetas **antes de Create bucket**. Conserva Object Ownership, el cifrado predeterminado y las cuatro opciones de Block Public Access habilitadas.
4. Crea el bucket y mantenlo vacío. No cargues archivos ni edites su política. Si no puedes incluir las etiquetas al crearlo, pide ayuda al instructor; no crees un bucket sin etiquetas.
5. Abre **SQS → Create queue**. Selecciona **Standard**, usa exactamente `user01-Queue` y agrega ambas etiquetas antes de confirmar.
6. Mantén habilitado el cifrado **SSE-SQS**. Conserva la política de acceso predeterminada; crea la cola y mantenla vacía.
7. Copia la URL y el ARN de la cola desde sus detalles. Guarda localmente una copia de la política original para restaurarla.

Block Public Access de S3 a nivel de cuenta permanece habilitado. Cambiar solo la protección del bucket no hace público este bucket vacío. La política pública de la cola puede introducir exposición real; habilita la regla primero y mantén la cola vacía.

## 4. Implementa el código de corrección de tu grupo

Configura `OWNER`, `NUMBER` y `ACCOUNT_ID`. Mantén `S3_BPA_EVENT = "PutBucketPublicAccessBlock"`, que coincide con el evento configurado en la regla. La rama de SQS comprueba la política y el cifrado en cada evento SetQueueAttributes. Elimina únicamente la instrucción pública con el nombre del ejercicio y conserva las demás. El límite del rol de ejecución exige las etiquetas de propietario; el código no tiene permiso para listar las etiquetas de la cola.

Si la prueba piloto muestra nombres distintos en los campos de la solicitud o falta queueUrl/bucketName, pide al instructor que adapte la extracción antes de la clase. No retires las comprobaciones de alcance. El código conserva el cifrado KMS existente; este laboratorio comienza con SSE-SQS y no incluye cambios de KMS.

```python
import json
import boto3

OWNER = "user01"
NUMBER = "01"
ACCOUNT_ID = "REPLACE_STORAGE_ACCOUNT_ID"
# Bucket-level CloudTrail event for updating S3 Block Public Access.
S3_BPA_EVENT = "PutBucketPublicAccessBlock"
BUCKET = f"workshop-{ACCOUNT_ID}-student-{NUMBER}-pythonshield"
QUEUE = f"{OWNER}-Queue"
QUEUE_ARN = f"arn:aws:sqs:us-east-1:{ACCOUNT_ID}:{QUEUE}"
s3 = boto3.client("s3", region_name="us-east-1")
sqs = boto3.client("sqs", region_name="us-east-1")


def lambda_handler(event, context):
    d = event.get("detail", {})
    p = d.get("requestParameters") or {}
    caller = f"arn:aws:iam::{ACCOUNT_ID}:user/workshop/{OWNER}"
    if (event.get("account") != ACCOUNT_ID or event.get("region") != "us-east-1"
            or d.get("userIdentity", {}).get("arn") != caller or "errorCode" in d):
        return {"outcome": "out_of_scope"}
    outcome = "already_compliant"
    if d.get("eventSource") == "s3.amazonaws.com" and d.get("eventName") == S3_BPA_EVENT:
        if p.get("bucketName") != BUCKET:
            return {"outcome": "out_of_scope"}
        resource = BUCKET
        settings = s3.get_public_access_block(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT_ID)["PublicAccessBlockConfiguration"]
        desired = {k: True for k in ("BlockPublicAcls", "IgnorePublicAcls",
                                    "BlockPublicPolicy", "RestrictPublicBuckets")}
        if not all(settings.get(k) for k in desired):
            s3.put_public_access_block(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT_ID,
                                      PublicAccessBlockConfiguration=desired)
            outcome = "bucket_protection_restored"
    elif d.get("eventSource") == "sqs.amazonaws.com" and d.get("eventName") == "SetQueueAttributes":
        url = sqs.get_queue_url(QueueName=QUEUE, QueueOwnerAWSAccountId=ACCOUNT_ID)["QueueUrl"]
        if p.get("queueUrl") != url:
            return {"outcome": "out_of_scope"}
        resource = QUEUE
        attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=[
            "QueueArn", "Policy", "SqsManagedSseEnabled", "KmsMasterKeyId"])["Attributes"]
        if attrs.get("QueueArn") != QUEUE_ARN:
            return {"outcome": "out_of_scope"}
        # IAM independently enforces the queue's immutable ownership tags.
        policy = json.loads(attrs.get("Policy") or '{"Version":"2012-10-17","Statement":[]}')
        statements = policy.get("Statement", [])
        if isinstance(statements, dict):
            statements = [statements]
        def exercise_public(s):
            principal = s.get("Principal")
            actions = s.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            return (s.get("Sid") == "WorkshopPublicSend" and s.get("Effect") == "Allow"
                    and (principal == "*" or principal == {"AWS": "*"})
                    and "sqs:SendMessage" in actions and s.get("Resource") == QUEUE_ARN)
        kept = [s for s in statements if not exercise_public(s)]
        changes = {}
        if len(kept) != len(statements):
            policy["Statement"] = kept
            changes["Policy"] = json.dumps(policy)
        if attrs.get("SqsManagedSseEnabled") != "true" and not attrs.get("KmsMasterKeyId"):
            changes["SqsManagedSseEnabled"] = "true"
        if changes:
            sqs.set_queue_attributes(QueueUrl=url, Attributes=changes)
            outcome = "queue_repair_requested"
    else:
        return {"outcome": "unsupported_event"}
    result = {"event_id": event.get("id"), "resource": resource, "outcome": outcome}
    print(json.dumps(result))
    return result
```

## 5. Conecta EventBridge con tu función

1. Abre **Amazon EventBridge → Rules → Create rule**. Usa el bus **default** y una regla basada en un patrón de eventos, no una programación.
2. Usa el prefijo de tu usuario en el nombre indicado abajo. Si es necesario, utiliza Advanced Builder o el editor de patrones JSON personalizados.
3. Pega el patrón y sustituye `ACCOUNT_ID` y `user01`. El patrón de Storage ya incluye `PutBucketPublicAccessBlock`; conserva ese nombre.
4. Selecciona el destino **AWS service → Lambda function → user01-Remediator**.
5. En los permisos del destino, selecciona **Use existing role → user01-EventRole**. Envía el **evento completo**, sin transformar la entrada.
6. Si el asistente propone crear un rol o agregar una política de recursos a Lambda, selecciona el rol existente. Si esa opción no aparece, consulta al instructor; no solicites permisos más amplios.
7. Agrega las etiquetas Workshop/Owner requeridas si el formulario de creación de la regla lo permite. Revisa y habilita la regla.

El filtro del usuario que realiza la llamada excluye las correcciones hechas por el rol de Lambda y ayuda a evitar ciclos. El filtro `errorCode` ignora llamadas fallidas. El controlador vuelve a comprobar el alcance y el estado actual porque los eventos pueden duplicarse o llegar con retraso.
Crea la regla **`user01-Storage`**. Envía los eventos de API de S3 y SQS a una función. Las ramas `$or` relacionan cada nombre de evento con su servicio. Prueba el patrón con los eventos de ejemplo del instructor.

```json
{
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
  },
  "$or": [
    {
      "source": [
        "aws.s3"
      ],
      "detail": {
        "eventSource": [
          "s3.amazonaws.com"
        ],
        "eventName": [
          "PutBucketPublicAccessBlock"
        ]
      }
    },
    {
      "source": [
        "aws.sqs"
      ],
      "detail": {
        "eventSource": [
          "sqs.amazonaws.com"
        ],
        "eventName": [
          "SetQueueAttributes"
        ]
      }
    }
  ]
}
```

## 6. Realiza los ejercicios, uno a la vez


### Ejercicio 8 — Block Public Access del bucket

1. Abre tu bucket → **Permissions → Block public access → Edit**.
2. Deshabilita las opciones a nivel de bucket, guarda y acepta la confirmación.
3. Actualiza: las cuatro opciones deben quedar habilitadas nuevamente. La protección a nivel de cuenta permanece habilitada.

### Ejercicio 9 — Política pública de SQS para SendMessage

1. Abre tu cola → **Edit → Access policy**.
2. Conserva la política existente. Agrega este objeto a su arreglo `Statement` y sustituye el ID de cuenta y el usuario:

```json
{
  "Sid": "WorkshopPublicSend",
  "Effect": "Allow",
  "Principal": "*",
  "Action": "sqs:SendMessage",
  "Resource": "arn:aws:sqs:us-east-1:ACCOUNT_ID:user01-Queue"
}
```

3. Guarda con el cifrado habilitado. No envíes mensajes ni deshabilites el cifrado para probar acceso anónimo; el ejercicio detecta la configuración de la política.
4. Actualiza: **WorkshopPublicSend** debe desaparecer y las instrucciones originales deben conservarse. Si la corrección falla, elimina manualmente esa instrucción de inmediato.

### Ejercicio 10 — Cifrado de la cola

1. Abre tu cola → **Edit → Encryption**. Deshabilita el cifrado del lado del servidor y guarda.
2. Actualiza: el cifrado debe quedar habilitado con **Amazon SQS key (SSE-SQS)**.
3. Espera la propagación de los atributos antes de evaluar el resultado. No necesitas una clave KMS.

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

Después de deshabilitar la regla, restaura la política privada original y el cifrado si es necesario. Elimina tu cola y bucket vacíos. Si la consola requiere una API ajena al ejercicio que esté denegada, pide al instructor que haga la limpieza sin ampliar tus permisos.
## Referencias

- https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-create-tag.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/configuring-block-public-access-bucket.html
- https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-add-permissions.html
- https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-sqs-sse-queue.html
- https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-create-pattern-operators.html
