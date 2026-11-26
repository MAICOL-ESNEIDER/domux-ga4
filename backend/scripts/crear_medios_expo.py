"""Crea las fotos, videos, audios y PDFs inventados para mostrar DOMUX en la exposición.

Todo se dibuja o se genera aquí mismo (no se baja de internet), así no hay problemas de derechos de autor.
Uso: python scripts/crear_medios_expo.py <carpeta_de_salida>
"""
import math, subprocess, sys, tempfile, os, wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
W, H = 800, 600
def font(size, bold=False):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",):
        if os.path.exists(p): return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)

def gradient(top, bottom, w=W, h=H):
    a = np.zeros((h, w, 3), dtype=np.uint8)
    for i in range(3):
        a[:, :, i] = np.linspace(top[i], bottom[i], h)[:, None]
    return Image.fromarray(a)

def banner(img, text):
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([0, img.height - 70, img.width, img.height], fill=(7, 17, 31, 215))
    d.text((24, img.height - 56), text, font=font(28, True), fill=(230, 244, 255))

def save(img, name):
    img.convert("RGB").save(OUT / name, "JPEG", quality=78, optimize=True)

def building(d, x, y, w, h, color=(34, 73, 120), windows=True):
    d.rectangle([x, y, x + w, y + h], fill=color)
    if windows:
        for r in range(int(h // 46)):
            for c in range(int(w // 40)):
                on = (r * 7 + c * 3) % 5 != 0
                d.rectangle([x + 12 + c * 40, y + 14 + r * 46, x + 32 + c * 40, y + 38 + r * 46], fill=(250, 214, 120) if on else (20, 40, 70))

# 1. Fuga de agua en el parqueadero
img = gradient((60, 66, 78), (30, 34, 42)); d = ImageDraw.Draw(img)
d.rectangle([0, 360, W, H], fill=(52, 56, 64))
for x in range(0, W, 160): d.rectangle([x + 60, 420, x + 70, 560], fill=(240, 220, 90))
d.rectangle([0, 0, W, 90], fill=(78, 82, 92)); d.rectangle([330, 90, 350, 210], fill=(150, 150, 160)); d.ellipse([318, 200, 362, 224], fill=(120, 120, 130))
for i, y in enumerate((236, 290, 340)): d.ellipse([336, y, 346, y + 18], fill=(90, 170, 240))
d.ellipse([220, 440, 520, 520], fill=(70, 120, 180, 255)); d.ellipse([260, 452, 480, 506], fill=(100, 160, 220))
banner(img, "Fuga de agua en el sótano 1"); save(img, "fuga-agua-sotano.jpg")

# 2. Bombillo dañado en el pasillo
img = gradient((26, 30, 44), (12, 14, 24)); d = ImageDraw.Draw(img)
d.polygon([(0, 600), (800, 600), (560, 330), (240, 330)], fill=(44, 48, 62))
d.rectangle([240, 150, 560, 330], fill=(34, 38, 52))
for x in (260, 380, 500): d.rectangle([x, 200, x + 50, 330], fill=(70, 56, 46))
d.line([(400, 0), (400, 110)], fill=(120, 120, 130), width=4); d.ellipse([374, 108, 426, 160], fill=(60, 60, 66), outline=(100, 100, 108), width=3)
d.text((300, 236), "PISO 4", font=font(30, True), fill=(120, 160, 200))
banner(img, "Lámpara apagada en el pasillo del piso 4"); save(img, "lampara-pasillo.jpg")

# 3. Paquetes en portería
img = gradient((226, 232, 240), (186, 196, 212)); d = ImageDraw.Draw(img)
d.rectangle([0, 380, W, H], fill=(120, 90, 66)); d.rectangle([0, 360, W, 392], fill=(150, 112, 80))
for (x, y, w, h, c) in ((90, 240, 190, 130, (196, 150, 98)), (310, 200, 230, 170, (182, 136, 86)), (570, 270, 150, 100, (206, 160, 106))):
    d.rectangle([x, y, x + w, y + h], fill=c); d.rectangle([x + w // 2 - 8, y, x + w // 2 + 8, y + h], fill=(224, 196, 150))
    d.rectangle([x + 14, y + h - 44, x + 80, y + h - 14], fill=(250, 250, 250)); d.line([(x + 20, y + h - 36), (x + 72, y + h - 36)], fill=(60, 60, 60), width=2); d.line([(x + 20, y + h - 26), (x + 60, y + h - 26)], fill=(60, 60, 60), width=2)
banner(img, "Paquetes recibidos en la portería"); save(img, "paquetes-porteria.jpg")

# 4. Carro mal parqueado
img = gradient((120, 126, 138), (72, 76, 86)); d = ImageDraw.Draw(img)
for x in (100, 400, 700): d.rectangle([x - 6, 200, x + 6, H], fill=(245, 245, 245))
d.rounded_rectangle([230, 300, 560, 440], radius=38, fill=(190, 40, 48)); d.polygon([(290, 300), (340, 238), (480, 238), (520, 300)], fill=(160, 30, 38))
d.polygon([(310, 300), (348, 252), (400, 252), (400, 300)], fill=(170, 210, 240)); d.polygon([(412, 300), (412, 252), (470, 252), (500, 300)], fill=(170, 210, 240))
for cx in (300, 500): d.ellipse([cx - 36, 408, cx + 36, 480], fill=(24, 24, 28)); d.ellipse([cx - 16, 428, cx + 16, 460], fill=(160, 160, 170))
d.rectangle([380, 396, 460, 424], fill=(250, 220, 60)); d.text((386, 398), "KLM 482", font=font(20, True), fill=(20, 20, 20))
banner(img, "Vehículo ocupando dos espacios"); save(img, "carro-mal-parqueado.jpg")

# 5. Salón comunal decorado
img = gradient((255, 236, 214), (240, 196, 160)); d = ImageDraw.Draw(img)
d.rectangle([0, 430, W, H], fill=(176, 130, 92))
for i, c in enumerate(((230, 70, 90), (70, 150, 230), (250, 190, 50), (110, 200, 120), (180, 100, 220), (240, 120, 60))):
    x = 120 + i * 110; d.line([(x, 150 + (i % 2) * 30), (x + 10, 400)], fill=(90, 90, 90), width=2); d.ellipse([x - 38, 70 + (i % 2) * 30, x + 38, 170 + (i % 2) * 30], fill=c)
d.rectangle([180, 360, 620, 400], fill=(250, 250, 250)); d.rectangle([180, 400, 620, 420], fill=(200, 200, 210))
for x in (230, 330, 430, 530): d.ellipse([x, 330, x + 50, 360], fill=(240, 90, 110))
banner(img, "Salón comunal listo para el evento"); save(img, "salon-comunal.jpg")

# 6. Piscina
img = gradient((150, 214, 250), (210, 238, 252)); d = ImageDraw.Draw(img)
d.rectangle([0, 260, W, H], fill=(60, 170, 220))
for r in range(8):
    for c in range(14): d.arc([c * 70 - 20 + (r % 2) * 30, 280 + r * 36, c * 70 + 40 + (r % 2) * 30, 312 + r * 36], 200, 340, fill=(190, 236, 252), width=3)
d.rectangle([0, 230, W, 262], fill=(232, 224, 206)); d.rectangle([660, 140, 676, 260], fill=(200, 200, 210)); d.rectangle([700, 140, 716, 260], fill=(200, 200, 210)); d.arc([660, 110, 716, 170], 180, 360, fill=(200, 200, 210), width=8)
banner(img, "Piscina de la unidad"); save(img, "piscina.jpg")

# 7. Ascensor averiado
img = gradient((200, 206, 216), (150, 158, 172)); d = ImageDraw.Draw(img)
d.rectangle([220, 90, 580, 520], fill=(176, 184, 196), outline=(110, 118, 130), width=6); d.rectangle([250, 120, 400, 520], fill=(206, 212, 222)); d.rectangle([400, 120, 550, 520], fill=(196, 202, 214)); d.line([(400, 120), (400, 520)], fill=(110, 118, 130), width=4)
d.rectangle([590, 250, 640, 330], fill=(40, 44, 54)); d.ellipse([600, 262, 630, 292], fill=(220, 60, 60))
d.rectangle([300, 270, 500, 350], fill=(250, 214, 60)); d.text((318, 284), "FUERA DE", font=font(30, True), fill=(30, 30, 30)); d.text((340, 316), "SERVICIO", font=font(24, True), fill=(30, 30, 30))
banner(img, "Ascensor de la Torre 2 fuera de servicio"); save(img, "ascensor-fuera-de-servicio.jpg")

# 8. Cartel de comunicado: jornada de fumigación
img = gradient((14, 40, 80), (7, 17, 31)); d = ImageDraw.Draw(img)
building(d, 60, 250, 180, 350); building(d, 270, 180, 200, 420, (40, 88, 140)); building(d, 500, 280, 220, 320, (30, 66, 110))
d.text((60, 56), "JORNADA DE", font=font(54, True), fill=(230, 244, 255)); d.text((60, 118), "FUMIGACIÓN", font=font(54, True), fill=(56, 189, 248))
banner(img, "Sábado, 7:00 a. m. · Todas las torres"); save(img, "aviso-fumigacion.jpg")

# 9. Zona de basuras
img = gradient((196, 214, 190), (150, 176, 146)); d = ImageDraw.Draw(img)
d.rectangle([0, 400, W, H], fill=(130, 140, 124))
for i, c in enumerate(((60, 150, 90), (60, 110, 200), (50, 50, 56))):
    x = 130 + i * 220; d.rectangle([x, 270, x + 150, 440], fill=c); d.rectangle([x - 8, 252, x + 158, 278], fill=tuple(max(0, v - 30) for v in c))
    d.text((x + 36, 340), ["ORG.", "RECIC.", "RESID."][i], font=font(22, True), fill=(250, 250, 250))
banner(img, "Punto de reciclaje del bloque B"); save(img, "punto-reciclaje.jpg")

# ---------- Videos ----------
def make_video(name, painter, seconds=4, fps=15, size=(640, 360)):
    with tempfile.TemporaryDirectory() as t:
        n = seconds * fps
        for i in range(n):
            im = painter(i / n, size); im.convert("RGB").save(f"{t}/f{i:03d}.jpg", quality=80)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", f"{t}/f%03d.jpg", "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(OUT / name)], check=True)

def goteo(p, size):
    im = gradient((60, 66, 78), (30, 34, 42), *size); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, size[0], 60], fill=(78, 82, 92)); d.rectangle([300, 60, 316, 150], fill=(150, 150, 160))
    for k in range(3):
        q = (p * 3 + k / 3) % 1; y = 150 + q * 160; d.ellipse([302, y, 314, y + 18], fill=(90, 170, 240))
    pool = 30 + 80 * p; d.ellipse([308 - pool, 320 - pool / 4, 308 + pool, 320 + pool / 4], fill=(70, 120, 180))
    d.text((16, size[1] - 40), "Fuga en el sótano 1", font=font(22, True), fill=(230, 244, 255)); return im
make_video("video-fuga-agua.mp4", goteo)

def piscina(p, size):
    im = gradient((150, 214, 250), (60, 170, 220), *size); d = ImageDraw.Draw(im)
    for r in range(7):
        for c in range(12):
            off = math.sin((p * 2 * math.pi) + r) * 14
            d.arc([c * 64 - 20 + off, 120 + r * 34, c * 64 + 40 + off, 150 + r * 34], 200, 340, fill=(200, 240, 252), width=3)
    d.text((16, size[1] - 40), "Piscina · revisión semanal", font=font(22, True), fill=(10, 40, 70)); return im
make_video("video-piscina.mp4", piscina)

# ---------- Audios ----------
def audio(name, notes, tail=0.15):
    sr = 22050; sig = []
    for freq, dur in notes:
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        env = np.minimum(1, np.minimum(t / 0.02, (dur - t) / 0.08 + 0.001)).clip(0, 1) * np.exp(-1.6 * t / dur)
        sig.append((np.sin(2 * math.pi * freq * t) * 0.5 + np.sin(2 * math.pi * freq * 2 * t) * 0.15) * env if freq else np.zeros_like(t))
        sig.append(np.zeros(int(sr * tail)))
    data = (np.concatenate(sig) * 32000).astype(np.int16)
    with tempfile.TemporaryDirectory() as t:
        wav = f"{t}/a.wav"
        with wave.open(wav, "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(data.tobytes())
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-c:a", "aac", "-b:a", "40k", "-f", "ipod", str(OUT / name)], check=True)
audio("audio-timbre-porteria.m4a", [(659, 0.5), (523, 0.9), (659, 0.5), (523, 0.9)], 0.2)
audio("audio-ruido-vecino.m4a", [(196, 0.35), (0, 0.15), (196, 0.35), (0, 0.15), (220, 0.35), (0, 0.15), (196, 0.7), (147, 0.9)], 0.05)
audio("audio-sirena-alarma.m4a", [(880, 0.4), (660, 0.4)] * 4, 0.02)

# ---------- PDFs ----------
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "reportlab"], check=True)
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

def pdf(name, title, paragraphs):
    c = canvas.Canvas(str(OUT / name), pagesize=letter); w, h = letter
    c.setFillColorRGB(.03, .09, .16); c.rect(0, h - 80, w, 80, fill=1, stroke=0)
    c.setFillColorRGB(.9, .96, 1); c.setFont("Helvetica-Bold", 20); c.drawString(48, h - 50, title)
    c.setFillColorRGB(0, 0, 0); c.setFont("Helvetica", 11); y = h - 120
    for para in paragraphs:
        words, line = para.split(), ""
        for wd in words:
            if c.stringWidth(line + " " + wd, "Helvetica", 11) > w - 96: c.drawString(48, y, line.strip()); y -= 16; line = wd
            else: line += " " + wd
        c.drawString(48, y, line.strip()); y -= 26
    c.showPage(); c.save()

pdf("factura-reparacion-bomba.pdf", "Cotización: reparación de bomba de agua", [
    "Conjunto Residencial Altos del Parque (unidad de ejemplo).",
    "Descripción: cambio de sello mecánico y rodamientos de la bomba de presión de la Torre 1. Incluye mano de obra y prueba de funcionamiento.",
    "Valor total estimado: $1.850.000 COP (IVA incluido). Vigencia de la cotización: 15 días.",
    "Documento de ejemplo creado para la demostración de DOMUX. Los datos son inventados."])
pdf("acta-reunion-consejo.pdf", "Acta de reunión del consejo de administración", [
    "Fecha: primer martes del mes, 7:00 p. m., salón comunal.",
    "Temas: 1) Estado de la cartera. 2) Mantenimiento de ascensores. 3) Horarios de la piscina. 4) Solicitudes de los residentes.",
    "Decisiones: se aprueba el mantenimiento de los ascensores de la Torre 2 y se mantiene el horario actual de la piscina.",
    "Documento de ejemplo creado para la demostración de DOMUX. Los datos son inventados."])
pdf("soporte-pago-parqueadero.pdf", "Soporte de pago: parqueadero de visitantes", [
    "Apartamento: 302, Torre 1. Concepto: uso de parqueadero de visitantes por 2 noches.",
    "Valor: $20.000 COP. Estado: pagado.",
    "Documento de ejemplo creado para la demostración de DOMUX. Los datos son inventados."])
pdf("manual-uso-salon-comunal.pdf", "Reglas para usar el salón comunal", [
    "Reserva con mínimo 3 días de anticipación desde la app DOMUX.",
    "Capacidad máxima: 60 personas. La música debe terminar a las 11:00 p. m.",
    "Quien reserva entrega el salón limpio y sin daños. Documento de ejemplo para la demostración."])
print(sorted(p.name + " " + str(p.stat().st_size // 1024) + "KB" for p in OUT.iterdir()))
