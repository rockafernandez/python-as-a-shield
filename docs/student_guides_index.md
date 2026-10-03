# Taller de seguridad de AWS con Python — Índice de guías

## ¿Qué guía debo usar?

| Cuenta asignada | Guía | Ejercicios |
|---|---|---|
| Network | [Guía Network](network_student_guide.md) | SSH, RDP, entrada de todos los protocolos, IPv4 pública automática en subred |
| Identity | [Guía Identity](identity_student_guide.md) | AdministratorAccess, política en línea con comodines, claves de acceso |
| Storage | [Guía Storage](storage_student_guide.md) | Block Public Access del bucket, política pública de SQS, cifrado de SQS |

Cada guía es independiente y aplica a user01–user10. Cada estudiante crea **una función Lambda en su cuenta asignada** para los casos de su grupo. Se trabaja desde la consola; no se necesitan claves de acceso ni perfiles de CLI para ejecutar el código.

Los ejemplos usan user01 / participante 01. Sustitúyelos de forma consistente por tu usuario y número asignados. Los mismos nombres de usuario en cuentas diferentes corresponden a inicios de sesión independientes.

## Preparación del instructor antes de la clase

1. Comparte de forma privada únicamente la fila de credenciales con estado ready del estudiante y su guía. No distribuyas el CSV completo.
2. Proporciona el ID real de la cuenta y confirma us-east-1. Para Network, proporciona la VPC y el CIDR configurado de cada estudiante.
3. Confirma que ambas SCP, los roles, los límites de permisos y el registro de eventos de administración de CloudTrail están configurados.
4. Haz una prueba piloto con user01 en cada cuenta. Verifica que la consola permita enviar etiquetas y el límite al crear recursos, y seleccionar el rol existente en EventBridge con los permisos actuales.
5. Para Storage, usa el eventName `PutBucketPublicAccessBlock` para Block Public Access del bucket y proporciona eventos de ejemplo sin datos sensibles para todos los casos. Confirma que los campos de solicitud coincidan con los usados por los controladores.
6. Network y Storage tienen actualmente una cuota total de concurrencia de 10; los aumentos están pendientes. No ejecutes el límite de concurrencia para todas las cuentas hasta disponer de capacidad suficiente. Usa funciones cortas y un cambio a la vez por estudiante. El instructor supervisa errores, limitaciones y duración.
7. Estos controladores educativos no se han probado mediante integración en AWS. Verifica el estado final y que repetir un evento no produzca nuevas modificaciones antes de entregar las guías. No incluyen aprobación de producción, deduplicación persistente, manejo de eventos fallidos ni protección atómica ante cambios externos concurrentes.

## Evidencia esperada

Para cada caso asignado: identificador del recurso, captura del estado corregido, registro de corrección sin datos sensibles y repetición del evento que devuelva already_compliant. No incluyas secretos en capturas ni registros.

## Responsabilidades de limpieza

Los estudiantes deshabilitan sus reglas y eliminan únicamente los recursos propios permitidos. El instructor elimina los usuarios de prueba protegidos, funciones Lambda, registros, identidades de participantes, políticas, roles y la infraestructura de red final. Mantén ambas SCP adjuntas mientras existan identidades del taller.

Base: workshop_setup.md, revisión 3. Guías preparadas después del aprovisionamiento; no vuelven a ejecutar ese proceso ni modifican los permisos existentes. Los archivos de aprovisionamiento se administran por separado y no se incluyen en este repositorio.
