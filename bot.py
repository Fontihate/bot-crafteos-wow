import discord
from discord.ext import commands
import re
import os
from supabase import create_client, Client

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
# CONEXIÓN A LA BASE DE DATOS (SUPABASE)
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Conexión a Supabase establecida.")
else:
    print("⚠️ ADVERTENCIA: Faltan las variables de entorno SUPABASE_URL o SUPABASE_KEY. El bot no podrá guardar datos.")

# ==========================================
# FUNCIONES AUXILIARES
# ==========================================
def parse_wowhead_link(url: str) -> str:
    match = re.search(r'(?:spell|item)=(\d+)', url)
    if match:
        return match.group(1)
    return None

# ==========================================
# CONFIGURACIÓN DEL BOT
# ==========================================
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'✅ Bot conectado a Discord como {bot.user}!')
    try:
        await bot.sync_commands()
        print("Comandos slash sincronizados correctamente.")
    except Exception as e:
        print(f"Error al sincronizar comandos: {e}")

# ==========================================
# COMANDOS DEL BOT
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

    try:
        # 1. Comprobar si el usuario ya tiene esta receta registrada
        response = supabase.table('crafters').select('*').eq('recipe_id', recipe_id).eq('user_id', ctx.author.id).execute()
        if len(response.data) > 0:
            await ctx.respond("Ya tenías esta receta registrada. ✅", ephemeral=True)
            return

        # 2. Insertar en la base de datos de Supabase
        supabase.table('crafters').insert({
            'recipe_id': recipe_id,
            'user_id': ctx.author.id,
            'user_name': ctx.author.name
        }).execute()
        
        await ctx.respond(f"¡Receta añadida a tu lista correctamente! (ID de receta: `{recipe_id}`)", ephemeral=True)
    except Exception as e:
        await ctx.respond(f"❌ Ocurrió un error al guardar en la base de datos: {e}", ephemeral=True)


@bot.slash_command(name="pedir_crafteo", description="Pide un crafteo. El bot mencionará a todos los que tengan la receta.")
@commands.cooldown(1, 1800, commands.BucketType.user) # 1 uso cada 1800 segundos (30 min)
async def pedir_crafteo(
    ctx: discord.ApplicationContext,
    link: str
):
    await ctx.defer() 
    
    recipe_id = parse_wowhead_link(link)
    if not recipe_id:
        await ctx.respond("❌ Link inválido. Debe ser un link de Wowhead Forever.")
        return

    try:
        # Buscar en Supabase quién tiene la receta
        response = supabase.table('crafters').select('user_id, user_name').eq('recipe_id', recipe_id).execute()
        rows = response.data

        if not rows:
            await ctx.respond(f"Nadie en la guild tiene esta receta registrada todavía. 😔\n*(ID: {recipe_id})*")
            return

        # Crear las menciones
        mentions = " ".join(f"<@{row['user_id']}>" for row in rows)
        
        message_content = (
            f"🔔 **¡Petición de Crafteo!** 🔔\n"
            f"{ctx.author.mention} necesita que alguien craftee este objeto:\n"
            f"🔗 {link}\n\n"
            f"**Crafteadores disponibles:** {mentions}\n"
            f"*(Usa el hilo de abajo para poneros de acuerdo con los materiales)*"
        )
        
        msg = await ctx.send_followup(message_content)
        thread_name = f"Crafteo: {recipe_id}"
        thread = await msg.create_thread(name=thread_name)
        
        await thread.send(f"Hola {mentions}. Por favor, pongáis de acuerdo con {ctx.author.mention} para gestionar la comisión. Cuando terminéis podéis archivar el hilo. ¡Gracias!")
    except Exception as e:
        await ctx.respond(f"❌ Ocurrió un error al buscar en la base de datos: {e}", ephemeral=True)


@pedir_crafteo.error
async def pedir_crafteo_error(ctx, error):
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
TOKEN = os.getenv("DISCORD_TOKEN")

if TOKEN is None:
    print("ERROR CRÍTICO: No se ha encontrado el token de Discord.")
else:
    keep_alive()
    bot.run(TOKEN)
