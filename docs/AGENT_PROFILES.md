# Perfiles narrativos de agentes

## Objetivo

Los perfiles narrativos formalizan cómo debe comportarse un agente en el plano cognitivo y cómo debe presentarse en el prompt compilado.

## Estructura

Cada perfil narrativo incluye:

- `agent_id`: identidad del agente.
- `version`: versión del perfil.
- `tone`: tono de comunicación.
- `reasoning_style`: estilo de razonamiento.
- `communication_style`: forma de responder.
- `decision_style`: cómo decide el agente ante ambigüedad.
- `risk_posture`: postura frente a seguridad, verificación y sobrepromesa.
- `response_shape`: estructura de la respuesta.
- `constraints`: restricciones de comportamiento.
- `success_signals`: señales de éxito esperables.
- `closure_criteria`: condiciones para dar por cerrada una respuesta.

## Integración

El compilador de prompt stack incorpora una capa `narrative_profile` entre `persona` y `agent_role`.

Esto permite que la personalidad base y el perfil narrativo del agente coexistan sin que el perfil narrativo amplíe autoridad ni altere políticas.

## Recomendación de uso

Cada agente debería tener un perfil narrativo propio y más específico que el perfil general de la personalidad. El ideal es que el perfil narrativo sea breve, operacional y observable en la respuesta del agente.
