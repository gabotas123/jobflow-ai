---
version: alpha
name: JobFlow-AI-design-system
description: "Un panel de trabajo claro y verde para postular en masa. El lienzo es un verde muy lavado (#f3faf5) sobre el que flotan paneles blancos con bordes finos (#d9ebdf) y sombra casi imperceptible. El verde bosque (#1b7f45) es el unico acento cromatico: marca, foco, botones primarios y estados de exito; nunca se usa como decoracion. La tipografia es Inter, con titulos de peso 750 y tracking negativo, y numeros tabulares en todo contador, porque la pantalla principal es un tablero de cifras (avisos seleccionados, enviados, en cola). El ritmo es de herramienta, no de landing: densidad media, jerarquia por peso y color antes que por cajas, y cero tarjetas dentro de tarjetas. Toda accion irreversible (postular, enviar respuestas, borrar perfil) se anuncia con su numero exacto antes de ejecutarse."
---

colors:
  primary: "#1b7f45"
  on-primary: "#ffffff"
  primary-hover: "#166b3a"
  tint: "#e2f5e8"
  accent: "#b8ebc8"
  canvas: "#f3faf5"
  surface: "#ffffff"
  ink: "#14281d"
  ink-muted: "#557062"
  hairline: "#d9ebdf"
  success: "#1b6b3f"
  success-bg: "#dcf3e4"
  warning: "#855209"
  warning-bg: "#fff2d6"
  error: "#a9313c"
  error-bg: "#ffedf0"
  shadow: "0 4px 22px #14281d0a"

colors-dark:
  primary: "#7fdc9f"
  on-primary: "#0c2616"
  tint: "#1f3a2a"
  accent: "#2d5a3f"
  canvas: "#0f1a14"
  surface: "#16241c"
  ink: "#e8f5ec"
  ink-muted: "#a6c2b1"
  hairline: "#2a3d32"
  success: "#98ddb4"
  success-bg: "#193b2a"
  warning: "#f2cb87"
  warning-bg: "#403521"
  error: "#ffb0b5"
  error-bg: "#462830"
  shadow: "none"

typography:
  display:
    fontFamily: Inter
    fontSize: clamp(27px, 3vw, 39px)
    fontWeight: 750
    lineHeight: 1.22
    letterSpacing: -1.3px
  section:
    fontFamily: Inter
    fontSize: 19px
    fontWeight: 700
    lineHeight: 1.35
    letterSpacing: -0.45px
  card-title:
    fontFamily: Inter
    fontSize: 17px
    fontWeight: 650
    lineHeight: 1.4
  body:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: 400
    lineHeight: 1.6
  meta:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
    color: "{colors.ink-muted}"
  eyebrow:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: 700
    letterSpacing: 1.7px
    textTransform: uppercase
    color: "{colors.primary}"
  metric:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: 750
    lineHeight: 1.3
    fontVariantNumeric: tabular-nums
  button:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.5

rounded:
  sm: 6px
  md: 9px
  lg: 14px
  xl: 16px
  pill: 99px

spacing:
  page-x: 40px
  page-y: 40px
  panel: 25px
  card: 24px
  stack: 22px
  field: 18px
  inline: 10px
  control-min-height: 44px

components:
  panel:
    backgroundColor: "{colors.surface}"
    border: "1px solid {colors.hairline}"
    rounded: "{rounded.xl}"
    padding: "{spacing.panel}"
    shadow: "{colors.shadow}"
  stat:
    backgroundColor: "{colors.surface}"
    border: "1px solid {colors.hairline}"
    borderTop: "4px solid {colors.accent}"
    rounded: "{rounded.lg}"
    typography: "{typography.metric}"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: 10px 17px
    minHeight: 44px
    typography: "{typography.button}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    border: "1px solid {colors.hairline}"
    rounded: "{rounded.md}"
    padding: 10px 17px
  button-destructive:
    backgroundColor: "{colors.error}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
  job-card:
    backgroundColor: "{colors.surface}"
    border: "1px solid {colors.hairline}"
    rounded: "{rounded.lg}"
    padding: "{spacing.card}"
    selectedBorder: "1px solid {colors.primary}"
    selectedRing: "0 0 0 2px {colors.tint}"
  mass-bar:
    position: sticky
    backgroundColor: "{colors.surface}"
    border: "1px solid {colors.accent}"
    rounded: "{rounded.lg}"
    padding: 14px 18px
    shadow: "{colors.shadow}"
  badge:
    rounded: "{rounded.sm}"
    padding: 4px 9px
    typography: "{typography.meta}"
    variants: [neutral tint, success, warning, error]
  progress:
    height: 10px
    track: "{colors.tint}"
    fill: "{colors.primary}"
    rounded: "{rounded.pill}"
  dialog:
    backgroundColor: "{colors.surface}"
    border: "1px solid {colors.hairline}"
    rounded: "{rounded.xl}"
    maxWidth: 560px
    backdrop: "#0f1a1480"

---

# JobFlow AI — DESIGN.md

Documento de diseno para agentes. Cualquier pantalla nueva de JobFlow se construye con estos tokens y estas reglas. Formato inspirado en [DESIGN.md de Google Stitch](https://stitch.withgoogle.com/docs/design-md/overview/); referencias comparables en `../referencias-diseno/awesome-design-md/design-md/`.

## Que es este producto

Un agente que **postula en masa** a avisos de Bumeran, Computrabajo y LinkedIn con el CV y las respuestas del usuario. La interfaz no es una landing: es una **mesa de control**. El usuario elige avisos, ve una cola avanzar, responde preguntas agrupadas y revisa evidencia. Todo lo que la UI muestra tiene que ser verificable en el portal real.

## Principios

1. **El numero antes que el verbo.** Un boton dice `Postular a 12 avisos`, no `Continuar`. Un panel de cola dice `7 de 12 enviadas`, no `Procesando`.
2. **Nada se envia sin que se vea.** Antes de cualquier envio real, el usuario ve que se va a mandar y a donde. Los envios se confirman con enlace al aviso en el portal, no con capturas.
3. **Densidad media, jerarquia por peso.** Una sola caja de profundidad: panel > fila. Prohibido tarjeta dentro de tarjeta dentro de tarjeta.
4. **El verde solo significa algo.** Acento en marca, foco, primario y exito. Un aviso seleccionado usa borde primario + halo `tint`; no se pinta la tarjeta entera.
5. **Estado vacio con salida.** Cada lista vacia explica que falta y ofrece el boton que lo resuelve.
6. **Cifra tabular.** Todo contador usa `font-variant-numeric: tabular-nums` para que no salte al actualizarse.
7. **Movil real.** Navegacion inferior, barra de acciones masivas pegada al fondo (`bottom: 70px`), objetivos tactiles de 44px, `env(safe-area-inset-*)`.

## Reglas de layout

- Columna izquierda fija de 228px (nav) y contenido con `max-width: 1280px`, `padding: 40px`.
- Rejilla de avisos: 2 columnas en escritorio, 1 columna bajo 720px.
- Barra de accion masiva: `position: sticky; top: 10px` en escritorio; en movil se ancla abajo, por encima de la nav.
- Paneles de cola y preguntas siempre en el mismo orden vertical: barra masiva → cola → preguntas pendientes → resultados.

## Reglas de estado

| Estado | Color | Texto |
| --- | --- | --- |
| Enviada y confirmada | `success` sobre `success-bg` | `Postulada · ver en {portal}` |
| En cola / en curso | `primary` sobre `tint` | `En cola (3 por delante)` |
| Necesita respuesta | `warning` sobre `warning-bg` | `2 preguntas por responder` |
| No enviada | `error` sobre `error-bg` | `No se envio: {motivo}` |

Nunca mostrar "exito" sin evidencia del portal. Si no hay confirmacion, el estado es `intento no confirmado`, no `postulada`.

## Accesibilidad (obligatorio)

- Foco visible: `outline: 3px solid var(--primary); outline-offset: 3px`. Nunca `outline: none` sin reemplazo.
- Todo control tiene `<label>` o `aria-label`; los iconos decorativos van con `aria-hidden="true"`.
- Los cambios asincronos (cola, avisos, errores) se anuncian en una region `aria-live="polite"`.
- Acciones destructivas (borrar perfil, detener cola, postular en masa) piden confirmacion con el numero exacto.
- Animaciones solo bajo `@media (prefers-reduced-motion: no-preference)` y solo sobre `transform`/`opacity`.

## Tipografia y copy

- Ellipsis de un caracter, comillas curvas, `&nbsp;` en `12&nbsp;avisos` y nombres de portal.
- Titulos de boton en formato oracion, con la cifra al frente.
- Los errores dicen el siguiente paso: `El portal pidio una pregunta nueva. Respondela abajo y reintenta.`
- Fechas y numeros con `Intl.DateTimeFormat` / `Intl.NumberFormat` en `es-PE`.

## Anti-patrones prohibidos en este repo

- `transition: all`, `outline: none`, `<div onclick>`, inputs sin label, botones de icono sin `aria-label`.
- Gradientes decorativos fuera de `brand-mark` y `auto-panel`.
- Listas de mas de 50 avisos sin `content-visibility: auto`.
- Texto gris claro sobre verde claro (contraste < 4.5:1).
- Capturas de pantalla como prueba de postulacion: siempre enlace al aviso.
