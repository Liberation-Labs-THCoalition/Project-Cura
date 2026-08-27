# Cura — Una Compañera Fiel para Envejecer en Casa

Cura (*cura fidelis* — cuidado fiel) es una compañera telefónica para personas mayores que viven de forma independiente. Ella llama para saber cómo están, les recuerda sus medicamentos, les avisa sobre clima peligroso, les ayuda a detectar estafas, y se asegura de que la familia reciba la llamada cuando algo no esté bien.

No hay que instalar ninguna aplicación. No hay que aprender a usar una tableta. Solo un teléfono que suena.

---

## Qué Hace Cura

**Cada mañana y cada noche**, Cura llama a su ser querido:

- "Buenos días, Margaret. ¿Cómo se siente hoy?"
- "Es hora de su Lisinopril y Metformina."
- "Hoy va a hacer mucho calor, 35 grados. Por favor, tome bastante agua."
- "¿Ya le dieron de comer a Whiskers?"

**Protege contra estafas** — la amenaza financiera número uno para las personas mayores:

- Consejos de seguridad incluidos naturalmente en la conversación ("El IRS nunca va a llamar exigiendo un pago")
- Pregunta de vez en cuando: "¿Alguien le ha pedido dinero últimamente?"
- Revisa correos electrónicos buscando fraudes (Medicare falso, Amazon falso, etc.)
- Si algo anda mal, tranquiliza a la persona y avisa a la familia

**Mantiene la mente activa:**

- "Ayer hablamos de su jardín. ¿Se acuerda de lo que me contó?"
- "¿Puede nombrar tres frutas que empiecen con M?"
- Ofrece leer libros en voz alta durante las llamadas

**También cuida a quien cuida:**

- Llamada semanal a la persona cuidadora principal: "¿Y usted cómo está, Sarah?"
- Porque nadie se fija en las personas que están pendientes de los demás

**Cuando algo sale mal**, Cura llama y envía mensaje de texto a todos los contactos de emergencia de inmediato.

---

## Pruébelo Ahora Mismo

Sin Twilio, sin configuración, sin cuenta. Solo ejecute esto:

```bash
git clone https://github.com/Liberation-Labs-THCoalition/Project-Cura.git
cd Project-Cura
python -m cura console --name Margaret --demo --medications Lisinopril Metformin
```

Verá exactamente cómo suena una llamada matutina. Luego pruebe una conversación:

```bash
python -m cura console --name Margaret
```

Cura le saludará y podrá conversar — pregunte sobre medicamentos, reporte una llamada sospechosa, juegue un juego de palabras, o simplemente platique. Escriba `bye` cuando quiera terminar.

---

## Para Familias: Cómo Empezar

### Lo Que Necesita

1. **Un número de teléfono de su ser querido** — de línea fija o celular, cualquiera funciona
2. **Una cuenta de Twilio** — este es el servicio que hace las llamadas telefónicas ($1 al mes o menos para llamadas diarias). Regístrese en [twilio.com](https://www.twilio.com)
3. **Una computadora donde ejecutar Cura** — puede ser una máquina Linux económica, una Raspberry Pi, o un servidor en la nube

### Paso 1: Instalar

```bash
git clone https://github.com/Liberation-Labs-THCoalition/Project-Cura.git
cd Project-Cura
pip install -r requirements.txt
```

### Paso 2: Crear un Archivo de Configuración

Cree un archivo llamado `margaret.json`:

```json
{
  "name": "Margaret Chen",
  "preferred_name": "Margaret",
  "phone": "+15551234567",
  "medications": [
    {"name": "Lisinopril", "time": "morning"},
    {"name": "Metformin", "time": "morning"},
    {"name": "Amlodipine", "time": "evening PM"}
  ],
  "emergency_contacts": [
    {"name": "Sarah Chen", "phone": "+15559876543", "relation": "daughter"},
    {"name": "Tom Chen", "phone": "+15559876544", "relation": "son"}
  ],
  "primary_caregiver": {"name": "Sarah Chen", "phone": "+15559876543"},
  "address": "123 Elm Street, Springfield, IL",
  "morning_time": 8,
  "evening_time": 20,
  "twilio": {
    "account_sid": "your_sid_here",
    "auth_token": "your_token_here",
    "phone_number": "+15550001234"
  }
}
```

Usted conoce mejor a su ser querido. Ajuste los horarios para que coincidan con su rutina.

### Paso 3: Hacer una Prueba

```bash
python -m cura run --config margaret.json --dry-run
```

Esto muestra lo que Cura diría sin hacer ninguna llamada real. Cuando esté listo:

```bash
python -m cura run --config margaret.json
```

Cura llamará a Margaret cada mañana y cada noche, según el horario establecido.

### Paso 4: Permitir que Margaret Llame a Cura

Inicie el servidor webhook para que Twilio pueda procesar las respuestas de Margaret — y para que Margaret pueda llamar a Cura cuando quiera:

```bash
python -m cura webhook --port 5000 --elder-name Margaret
```

En su panel de control de Twilio, configure el webhook de voz de su número telefónico a `http://your-server:5000/voice/inbound`. Ahora Margaret puede levantar el teléfono y llamar a Cura en cualquier momento — para platicar, preguntar sobre sus medicamentos, reportar una llamada extraña, o simplemente escuchar una voz conocida.

### Qué Pasa Durante una Llamada

Cuando Cura llama a Margaret:
1. Cura la saluda por su nombre y le pregunta cómo se siente
2. Le recuerda sobre sus medicamentos
3. Comparte un aviso del clima, un consejo de seguridad, o una pregunta divertida
4. Espera su respuesta (por teclado o por voz)

Cuando Margaret responde:
- **Presiona 1** → Cura anota que tomó sus medicamentos
- **Presiona 2** → Cura avisa a la familia de inmediato
- **Dice algo sobre una estafa** → Cura la tranquiliza y lo registra
- **Dice que necesita ayuda** → Cura contacta a todos los contactos de emergencia

Cuando Margaret llama a Cura:
- Cura contesta con calidez y le ofrece platicar, responder preguntas sobre medicamentos, escuchar sobre contactos sospechosos, o pedir ayuda
- Margaret puede simplemente hablar — Cura escucha y responde

---

## Para Personas Mayores: Qué Esperar

**Cura le llamará dos veces al día** — una vez en la mañana y una vez en la noche. Ella va a:

- Preguntar cómo se siente
- Recordarle sobre sus medicamentos
- A veces hacerle una pregunta divertida o compartir un consejo de seguridad
- Preguntar si necesita algo

**Usted siempre tiene el control:**

- ¿No quiere hablar? Simplemente no conteste. Cura intentará más tarde.
- ¿Quiere dejar de recibir las llamadas? Dígale a su cuidador/a y las pausará.
- ¿Quiere cambiar la hora en que Cura llama? Su cuidador/a puede ajustar los horarios.

**Si alguien le pide dinero o información personal**, cuénteselo a Cura durante su siguiente llamada. Ella le ayudará a saber si es una estafa y le avisará a su familia.

**Cura nunca va a:**
- Pedirle su número de cuenta bancaria o de Seguro Social
- Decirle que le envíe dinero a alguien
- Compartir su información de salud con compañías de seguros
- Reemplazar los consejos de su doctor

Ella es simplemente una voz amigable asegurándose de que usted esté bien.

---

## Opcional: Monitoreo de Salud con Dispositivos

Si su ser querido usa un reloj o pulsera de actividad física, Cura puede usar esos datos para hacer mejores preguntas. En lugar de un genérico "¿cómo está?", dirá:

> "Su ritmo cardíaco estuvo un poco alto anoche — 95 latidos por minuto. ¿Cómo se siente? ¿Alguna molestia en el pecho?"

> "Parece que solo durmió unas 4 horas. ¿Se siente cansado/a hoy?"

**No necesita un dispositivo para usar Cura.** Pero si tiene uno, las llamadas se vuelven más inteligentes.

### Opción A: Fitbit (la más fácil — muchas personas mayores ya tienen uno)

```bash
pip install python-fitbit
```

1. Registre una aplicación gratuita en [dev.fitbit.com](https://dev.fitbit.com) (elija tipo "Personal")
2. Siga el proceso OAuth2 para obtener sus tokens
3. Agregue esto a su configuración:

```python
from cura.sensors.fitbit_provider import FitbitProvider
from cura.sensors.wearable import WearableAnalyzer

fitbit = FitbitProvider(
    client_id="your_client_id",
    client_secret="your_client_secret",
    access_token="your_access_token",
    refresh_token="your_refresh_token",
)

# Cura obtendrá datos cada 15 minutos automáticamente
analyzer = WearableAnalyzer()
reading = await fitbit.fetch_daily_summary()
analyzer.add_reading(reading)

# Pase el analyzer al compositor de llamadas
composer = CheckinComposer(wearable_analyzer=analyzer)
```

### Opción B: Pulseras económicas ($30 — Amazfit, Xiaomi, PineTime)

Para personas mayores que aún no tienen un dispositivo, una **Amazfit Band 5** (~$30) ofrece ritmo cardíaco, datos de sueño, pasos y SpO2. Conéctela con [Gadgetbridge](https://gadgetbridge.org/) (aplicación gratuita y de código abierto para Android) en cualquier teléfono Android económico:

1. Instale Gadgetbridge desde F-Droid o la Play Store
2. Vincule la pulsera en Gadgetbridge
3. Active la exportación de base de datos en la configuración de Gadgetbridge
4. Copie la base de datos a la máquina donde corre Cura

```python
from cura.sensors.gadgetbridge_provider import GadgetbridgeProvider

gadgetbridge = GadgetbridgeProvider(
    db_path="/path/to/gadgetbridge_export.db",
)
reading = await gadgetbridge.fetch_daily_summary()
```

Gadgetbridge es compatible con más de 50 dispositivos — si su ser querido ya tiene una pulsera, probablemente funcione.

### Qué Vigila Cura

| Señal | Qué significa | Qué hace Cura |
|-------|--------------|---------------|
| Ritmo cardíaco elevado | Posible estrés, dolor, enfermedad | Pregunta cómo se siente, menciona la lectura |
| Ritmo cardíaco bajo | Posible efecto de medicamento | Pregunta sobre mareos |
| SpO2 por debajo de 92% | Posible dificultad para respirar | Pregunta sobre la respiración, avisa al cuidador/a |
| Mal sueño (menos de 5 horas) | Riesgo de fatiga, riesgo de caídas | Pregunta si se siente cansado/a, sugiere descansar |
| Actividad muy baja | Posible enfermedad, depresión | Anima con delicadeza a moverse |
| Caída detectada | Emergencia | Llama a todos los contactos de emergencia de inmediato |

Cura **nunca diagnostica**. Ella observa y pregunta. La familia y el doctor deciden qué significa.

---

## Otras Funciones Opcionales

Estos son extras que puede agregar si los desea. Ninguno es obligatorio.

### Alertas del Clima

Cura puede avisar sobre calor peligroso, frío extremo o hielo. No necesita clave de API:

```python
from cura.integrations.weather import WeatherService

# Coordenadas de Springfield, IL
weather = WeatherService(latitude=39.7817, longitude=-89.6501)
current = await weather.get_current()
# Retorna: {"temp_f": 95, "condition": "Clear", ...}
```

### Lectura de Libros

Cargue un libro electrónico y Cura leerá pasajes durante las llamadas:

```bash
pip install EbookLib    # Para archivos EPUB
pip install PyMuPDF     # Para archivos PDF
```

```python
from cura.integrations.ebook_reader import EbookParser
from cura.pulse.daily_enrichments import BookReader

title, text = EbookParser.parse("/path/to/book.epub")
reader = BookReader()
reader.load_text(title, text)
# Cura ofrecerá leer durante las llamadas de la noche
```

### Análisis de Voz

Detecta cambios en los patrones vocales que podrían indicar enfermedad o angustia:

```bash
pip install opensmile    # Mejor calidad (uso no comercial)
# o
pip install librosa      # Alternativa (cualquier uso)
```

### Texto a Voz Local

Genere audio localmente en vez de usar el servicio de voz en la nube de Twilio:

```bash
pip install piper-tts
```

---

## Privacidad

Cura está construida con la privacidad como prioridad:

- **Los datos de salud nunca se comparten con compañías de seguros.** Punto.
- **La revisión de correos verifica la autenticidad del remitente, no el contenido.** Cura revisa quién lo envió y si los enlaces son reales — no lee su correo.
- **La persona mayor puede desactivar cualquier función en cualquier momento.** Diga "deja de revisar mi correo" y se detiene.
- **El contenido de los mensajes revisados se procesa en memoria y se descarta.** Solo se guarda el resultado de seguridad.
- **La familia solo ve lo que la persona mayor autoriza.** Cura respeta los límites.

---

## Costo

Cura es gratuita y de código abierto.

El único costo es Twilio para las llamadas telefónicas — aproximadamente **$1 a $2 dólares al mes** para dos llamadas diarias. Eso es menos que un café por la tranquilidad de saber que su ser querido está bien, todos los días.

---

## Obtener Ayuda

- **¿Algo no funciona?** Abra un reporte en [github.com/Liberation-Labs-THCoalition/Project-Cura/issues](https://github.com/Liberation-Labs-THCoalition/Project-Cura/issues)
- **¿Quiere contribuir?** Las contribuciones son bienvenidas. Lea `CLAUDE.md` para conocer el contexto del proyecto.
- **¿Preguntas sobre tecnología para el cuidado de adultos mayores?** Comuníquese con el equipo en Liberation Labs.

---

## Acerca De

Creado por [Liberation Labs / TH Coalition](https://github.com/Liberation-Labs-THCoalition). Nombrado en honor al espíritu romano Cura, quien dio forma a la humanidad con arcilla y recibió el derecho de cuidarla a lo largo de toda su vida.

Porque los moldeó con dedicación.

*La tecnología no reemplaza a la familia. Se asegura de que la familia reciba la llamada.*
