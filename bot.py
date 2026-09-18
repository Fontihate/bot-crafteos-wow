import discord
from discord.ext import commands
import sqlite3
import re
import os

# ==========================================
# CONFIGURACIÓN DE ROLES DE PROFESIONES
# ==========================================
# Pon aquí el nombre exacto del rol y la ID del rol entre comillas.
# Ejemplo: "Alquimia": 123456789012345678
# Deja la ID como "0" si aún no has creado el rol, y el bot no dará error.
ROLE_MAP = {
    "Herboristería": 1550430033703870544,
    "Minería": 1550429708305571891,
    "Desuello": 1550429747232641024,
    "Sastrería": 1550429610909368411,
    "Herrería": 1550429250216001536,
    "Alquimia": 1550429445373038592,
    "Ingeniería": 1550429481959694347,
    "Peletería": 1550429534581563402,
    "Encantamiento": 1550429647429304410,
    "Cocina": 1550429683483680829
}

# ==========================================
# SISTEMA DE BASE DE DATOS (SQLite)
# ==========================================
def init_db():
    conn = sqlite3.connect('crafts.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS crafters (
                    recipe_id TEXT,
                    user_id INTEGER,
                    user_name TEXT
                )''')
    conn.commit()
    conn.close()

# Inicializar la BD al arrancar
init_db()

# ==========================================
# FUNCIONES AUXILIARES
# ==========================================
def parse_wowhead_link(url: str) -> str:
    """Extrae el ID de la receta/objeto del link de Wowhead Forever."""
    match = re.search(r'(?:spell|item)=(\d+)', url)
    if match:
        return match.group(1)
    return None

# ==========================================
# CONFIGURACIÓN DEL BOT
# ==========================================
# Configurar los Intents (necesarios para leer miembros y asignar roles)
intents = discord.Intents.default()
intents.members = True

# Inicializar el bot
bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# EVENTOS DEL BOT
# ==========================================
@bot.event
async def on_ready():
    print(f'✅ Bot conectado correctamente como {bot.user}!')
    try:
        # Sincroniza los comandos slash al arrancar
        await bot.sync_commands()
        print("Comandos slash sincronizados correctamente.")
    except Exception as e:
        print(f"Error al sincronizar comandos: {e}")

# ==========================================
# COMANDOS DEL BOT (SLASH COMMANDS)
# ==========================================

@bot.slash_command(name="registrar_profesion", description="Registra tu profesión para obtener el rol del servidor.")
async def registrar_profesion(
    ctx: discord.ApplicationContext,
    profesion: discord.Option(str, choices=list(ROLE_MAP.keys()))
):
    role_id = ROLE_MAP.get(profesion)
    
    if role_id == 0:
        await ctx.respond("Esa profesión aún no tiene un rol configurado en el servidor. Avisa a un admin.", ephemeral=True)
        return

    role = ctx.guild.get_role(role_id)
    if not role:
        await ctx.respond("No encuentro el rol en el servidor. Revisa la configuración.", ephemeral=True)
        return

    try:
        await ctx.author.add_roles(role)
        await ctx.respond(f"¡Te he asignado el rol de **{profesion}**! 🛠️", ephemeral=True)
    except discord.Forbidden:
        await ctx.respond("No tengo permisos para darte roles. Mi rol debe estar por encima del tuyo.", ephemeral=True)


@bot.slash_command(name="añadir_crafteo", description="Añade una receta que sepas craftear usando el link de Wowhead Forever.")
async def añadir_crafteo(
    ctx: discord.ApplicationContext,
    link: str
):
    recipe_id = parse_wowhead_link(link)
    
    if not recipe_id:
        await ctx.respond("❌ Link inválido. Debe ser un link de Wowhead que contenga `spell=` o `item=`.\nEjemplo: `https://www.wowhead.com/forever/es/spell=16729/`", ephemeral=True)
        return

    conn = sqlite3.connect('crafts.db')
    c = conn.cursor()
    
    # Comprobar si ya lo tenía añadido
    c.execute("SELECT * FROM crafters WHERE recipe_id=? AND user_id=?", (recipe_id, ctx.author.id))
    if c.fetchone():
        await ctx.respond("Ya tenías esta receta registrada. ✅", ephemeral=True)
        conn.close()
        return

    # Insertar en la BD
    c.execute("INSERT INTO crafters (recipe_id, user_id, user_name) VALUES (?, ?, ?)", 
              (recipe_id, ctx.author.id, ctx.author.name))
    conn.commit()
    conn.close()
    
    await ctx.respond(f"¡Receta añadida a tu lista correctamente! (ID de receta: `{recipe_id}`)", ephemeral=True)


@bot.slash_command(name="pedir_crafteo", description="Pide un crafteo. El bot mencionará a todos los que tengan la receta.")
@commands.cooldown(1, 1800, commands.BucketType.user) # 1 uso cada 1800 segundos (30 min)
async def pedir_crafteo(
    ctx: discord.ApplicationContext,
    link: str
):
    # Esperamos un poco porque la BD tarda en responder
    await ctx.defer() 
    
    recipe_id = parse_wowhead_link(link)
    if not recipe_id:
        await ctx.respond("❌ Link inválido. Debe ser un link de Wowhead Forever.")
        return

    conn = sqlite3.connect('crafts.db')
    c = conn.cursor()
    c.execute("SELECT user_id, user_name FROM crafters WHERE recipe_id=?", (recipe_id,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        await ctx.respond(f"Nadie en la guild tiene esta receta registrada todavía. 😔\n*(ID: {recipe_id})*")
        return

    # Crear las menciones
    mentions = " ".join(f"<@{row[0]}>" for row in rows)
    
    # Mensaje principal
    message_content = (
        f"🔔 **¡Petición de Crafteo!** 🔔\n"
        f"{ctx.author.mention} necesita que alguien craftee este objeto:\n"
        f"🔗 {link}\n\n"
        f"**Crafteadores disponibles:** {mentions}\n"
        f"*(Usa el hilo de abajo para poneros de acuerdo con los materiales)*"
    )
    
    # Enviar el mensaje y crear el hilo
    msg = await ctx.send_followup(message_content)
    thread_name = f"Crafteo: {recipe_id}"
    thread = await msg.create_thread(name=thread_name)
    
    # Mensaje automático dentro del hilo
    await thread.send(f"Hola {mentions}. Por favor, pongáis de acuerdo con {ctx.author.mention} para gestionar la comisión. Cuando terminéis podéis archivar el hilo. ¡Gracias!")


@pedir_crafteo.error
async def pedir_crafteo_error(ctx, error):
    # Manejo del cooldown (antispam)
    if isinstance(error, commands.CommandOnCooldown):
        mins = int(error.retry_after // 60)
        secs = int(error.retry_after % 60)
        await ctx.respond(f"⏳ Para evitar spam, solo puedes pedir un crafteo cada 30 minutos. Prueba en {mins} minutos y {secs} segundos.", ephemeral=True)
    else:
        await ctx.respond(f"Ocurrió un error inesperado: {error}", ephemeral=True)


# ==========================================
# SERVIDOR WEB FALSO PARA RENDER (FREE TIER)
# ==========================================
from flask import Flask
from threading import Thread

# Creamos una web falsa para que Render no nos apague por inactividad
app = Flask('')

@app.route('/')
def home():
    return "Bot de WoW funcionando correctamente."

def run_web():
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()


# ==========================================
# INICIAR EL BOT
# ==========================================
# Render inyectará el token en una variable de entorno
TOKEN = os.getenv("DISCORD_TOKEN")

if TOKEN is None:
    print("ERROR CRÍTICO: No se ha encontrado el token de Discord.")
    print("Asegúrate de configurar la variable de entorno 'DISCORD_TOKEN' en Render.")
else:
    keep_alive() # Levantamos la web
    bot.run(TOKEN) # Encendemos el bot
