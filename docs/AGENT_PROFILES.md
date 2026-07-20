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
- `constraints`: restricciones de comportamiento.
- `success_signals`: señales de éxito esperables.

## Integración

El compilador de prompt stack incorpora una capa `narrative_profile` entre `persona` y `agent_role`.

Esto permite que la personalidad base y el perfil narrativo del agente coexistan sin que el perfil narrativo amplíe autoridad ni altere políticas.
