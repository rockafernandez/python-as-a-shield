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
# Serializa los resultados en JSON para facilitar su lectura en CloudWatch Logs.
import json
# Boto3 permite llamar a las API de AWS con las credenciales temporales del rol de Lambda.
import boto3

# Configuración del participante: sustituye estos valores por los de tu cuenta y usuario.
# Los nombres exactos delimitan los recursos que esta función puede corregir.
OWNER = "user01"
NUMBER = "01"
ACCOUNT_ID = "REPLACE_STORAGE_ACCOUNT_ID"
# Nombre de CloudTrail para actualizar Block Public Access de un bucket.
# Difiere del nombre de la operación de Boto3: put_public_access_block.
S3_BPA_EVENT = "PutBucketPublicAccessBlock"
BUCKET = f"workshop-{ACCOUNT_ID}-student-{NUMBER}-pythonshield"
QUEUE = f"{OWNER}-Queue"
QUEUE_ARN = f"arn:aws:sqs:us-east-1:{ACCOUNT_ID}:{QUEUE}"
# Reutiliza los clientes de S3 y SQS durante la vida del entorno de Lambda.
s3 = boto3.client("s3", region_name="us-east-1")
sqs = boto3.client("sqs", region_name="us-east-1")


# Punto de entrada de Lambda. EventBridge entrega el evento completo en event;
# context contiene información de la ejecución y no se necesita en este ejemplo.
def lambda_handler(event, context):
    # El sobre de EventBridge contiene cuenta, región e identificador del evento.
    # detail contiene la llamada registrada por CloudTrail: servicio, usuario y parámetros.
    d = event.get("detail", {})
    # Los parámetros permiten identificar el bucket o la URL de la cola modificada.
    p = d.get("requestParameters") or {}
    # Construye el ARN del participante que debe haber provocado el cambio.
    # Las llamadas del rol de esta Lambda quedan fuera de alcance, evitando ciclos.
    caller = f"arn:aws:iam::{ACCOUNT_ID}:user/workshop/{OWNER}"
    # Rechaza eventos de otra cuenta, región o identidad y llamadas que fallaron.
    # Esta validación se repite aquí aunque la regla de EventBridge también filtre eventos.
    if (event.get("account") != ACCOUNT_ID or event.get("region") != "us-east-1"
            or d.get("userIdentity", {}).get("arn") != caller or "errorCode" in d):
        return {"outcome": "out_of_scope"}
    # Por defecto no hay cambios: los eventos repetidos deben ser seguros de procesar.
    outcome = "already_compliant"
    # Caso S3: solo procesa el cambio de Block Public Access del bucket asignado.
    if d.get("eventSource") == "s3.amazonaws.com" and d.get("eventName") == S3_BPA_EVENT:
        if p.get("bucketName") != BUCKET:
            return {"outcome": "out_of_scope"}
        resource = BUCKET
        # Consulta la configuración actual, en lugar de asumir que sigue igual al evento.
        # ExpectedBucketOwner exige que el bucket pertenezca a la cuenta configurada.
        settings = s3.get_public_access_block(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT_ID)["PublicAccessBlockConfiguration"]
        # Estado esperado: habilitar las cuatro protecciones de acceso público.
        # BlockPublicAcls rechaza ACL públicas e IgnorePublicAcls ignora ACL públicas existentes.
        # BlockPublicPolicy rechaza políticas públicas y RestrictPublicBuckets restringe
        # el acceso de buckets con políticas públicas. Solo se modifica el nivel de bucket.
        desired = {k: True for k in ("BlockPublicAcls", "IgnorePublicAcls",
                                    "BlockPublicPolicy", "RestrictPublicBuckets")}
        # Restaura las cuatro opciones si falta alguna; si ya están activas, no escribe.
        if not all(settings.get(k) for k in desired):
            s3.put_public_access_block(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT_ID,
                                      PublicAccessBlockConfiguration=desired)
            outcome = "bucket_protection_restored"
    # Caso SQS: SetQueueAttributes puede cambiar la política o el cifrado.
    # En cada evento se revisan ambos atributos, independientemente de cuál cambió.
    elif d.get("eventSource") == "sqs.amazonaws.com" and d.get("eventName") == "SetQueueAttributes":
        # Resuelve la URL de la cola en la cuenta esperada y la compara con el evento.
        url = sqs.get_queue_url(QueueName=QUEUE, QueueOwnerAWSAccountId=ACCOUNT_ID)["QueueUrl"]
        if p.get("queueUrl") != url:
            return {"outcome": "out_of_scope"}
        resource = QUEUE
        # Lee el ARN, la política y las modalidades de cifrado del estado actual.
        attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=[
            "QueueArn", "Policy", "SqsManagedSseEnabled", "KmsMasterKeyId"])["Attributes"]
        if attrs.get("QueueArn") != QUEUE_ARN:
            return {"outcome": "out_of_scope"}
        # El ARN debe coincidir exactamente con la cola asignada.
        # Los permisos de IAM también exigen sus etiquetas de pertenencia protegidas.
        # La función no necesita consultar las etiquetas con otra llamada a SQS.
        policy = json.loads(attrs.get("Policy") or '{"Version":"2012-10-17","Statement":[]}')
        # Normaliza Statement a una lista: JSON admite una instrucción o varias.
        statements = policy.get("Statement", [])
        if isinstance(statements, dict):
            statements = [statements]
        # Reconoce únicamente la instrucción pública específica del laboratorio:
        # Sid esperado, Allow, principal público, SendMessage y ARN de esta cola.
        # No pretende detectar todas las variantes de políticas públicas de producción.
        def exercise_public(s):
            principal = s.get("Principal")
            actions = s.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            return (s.get("Sid") == "WorkshopPublicSend" and s.get("Effect") == "Allow"
                    and (principal == "*" or principal == {"AWS": "*"})
                    and "sqs:SendMessage" in actions and s.get("Resource") == QUEUE_ARN)
        # Conserva todas las instrucciones ajenas al ejercicio y elimina solo la coincidente.
        kept = [s for s in statements if not exercise_public(s)]
        # Acumula únicamente los atributos que necesitan corrección para enviarlos juntos.
        changes = {}
        if len(kept) != len(statements):
            policy["Statement"] = kept
            changes["Policy"] = json.dumps(policy)
        # Activa SSE-SQS si está deshabilitado y no hay una clave KMS configurada.
        # Conserva el cifrado KMS existente; no lo reemplaza por SSE-SQS.
        if attrs.get("SqsManagedSseEnabled") != "true" and not attrs.get("KmsMasterKeyId"):
            changes["SqsManagedSseEnabled"] = "true"
        # Si no hay diferencias, evita una escritura. La API acepta las correcciones;
        # confirma después en la consola el estado de la política y del cifrado.
        if changes:
            sqs.set_queue_attributes(QueueUrl=url, Attributes=changes)
            outcome = "queue_repair_requested"
    else:
        # Otros servicios o nombres de evento no tienen una corrección definida aquí.
        return {"outcome": "unsupported_event"}
    # Registra únicamente el identificador, el recurso y el resultado de la corrección.
    # No imprime el evento completo ni credenciales. Devuelve el mismo resumen al invocador.
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
