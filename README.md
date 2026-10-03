# Python as a Shield

Taller práctico de nivel intermedio sobre corrección automática de configuraciones de seguridad en AWS con **Python, Boto3, Lambda y EventBridge**.

Cada participante crea recursos, provoca una configuración insegura controlada y verifica su corrección automática. Se utilizan tres cuentas miembro dedicadas, con diez usuarios por cuenta, en **us-east-1**.

## Guías del taller

| Grupo | Casos | Guía |
|---|---|---|
| Network | SSH público, RDP público, entrada pública de todos los protocolos, IPv4 pública automática en subred | [Guía Network](docs/network_student_guide.md) |
| Identity | AdministratorAccess, política en línea con comodines, creación de claves de acceso | [Guía Identity](docs/identity_student_guide.md) |
| Storage | Block Public Access del bucket, política pública de SQS, cifrado de SQS | [Guía Storage](docs/storage_student_guide.md) |

Consulta el [índice de guías y preparación del instructor](docs/student_guides_index.md).

## Cómo empezar

1. Recibe del instructor tus credenciales individuales, la cuenta y el grupo asignados.
2. Sigue únicamente la guía de tu grupo. Los ejemplos usan `user01` y `01`; sustitúyelos por tu usuario y número.
3. Incluye `Workshop=true` y `Owner=tu-usuario` al crear los recursos.
4. Crea una función Lambda con tu rol existente y configura su regla de EventBridge.
5. Prueba un caso a la vez, verifica el estado final y repite el evento para comprobar que no se modifica un recurso ya corregido.
6. Guarda evidencia sin datos sensibles y sigue los pasos de limpieza.

Los nombres de recursos, comandos y código se conservan para mantener compatibilidad. Las opciones de la consola se muestran en inglés para facilitar su identificación.

## Antes de la clase

El instructor debe probar un usuario de cada grupo, confirmar los permisos y CloudTrail, y proporcionar los valores reales requeridos. Storage usa el evento de CloudTrail `PutBucketPublicAccessBlock` para actualizar Block Public Access del bucket.

El código es educativo y no se ha validado mediante integración en estas cuentas. Usa cuentas de laboratorio, recursos vacíos y eventos de ejemplo sin datos sensibles. La corrección es reactiva: puede existir una ventana temporal de exposición.

Este repositorio contiene únicamente el README y las guías. No publiques contraseñas, el CSV de credenciales, claves de acceso ni tokens de sesión.
