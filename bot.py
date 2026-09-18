import discord
from discord.ext import commands
from discord import app_commands
import re
import os
import time
from supabase import create_client, Client
from flask import Flask
from threading import Thread

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
    print("⚠️ ADVERTENCIA: Faltan las variables de entorno SUPABASE.")

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

# Control de spam (Cooldown manual)
cooldowns = {}
COOLDOWN_TIME = 1800 # 30 minutos en segundos

@bot.event
async def on_ready():
    print(f'✅ Bot conectado a Discord como {bot.user}!')
    try:
        synced = await bot.tree.sync()
        print(f"Comandos slash sincronizados: {len(synced)}")
    except Exception as e:
        print(f"Error al sincronizar comandos: {e}")

# ==========================================
# COMANDOS DEL BOT
# ==========================================

@bot.tree.command(name="registrar_profesion", description="Registra tu profesión para obtener el rol del servidor.")
@app_commands.choices(profesion=[app_commands.Choice(name=k, value=k) for k in ROLE_MAP.keys()])
async def registrar_profesion(interaction: discord.Interaction, profesion: app_commands.Choice[str]):
    role_id = ROLE_MAP.get(profesion.value)
    
    if role_id == 0:
        await interaction.response.send_message("Esa profesión aún no tiene un rol configurado. Avisa a un admin.", ephemeral=True)
        return

    role = interaction.guild.get_role(role_id)
    if not role:
        await interaction.response.send_message("No encuentro el rol en el servidor.", ephemeral=True)
        return

    try:
        await interaction.user.add_roles(role)
        await interaction.response.send_message(f"¡Te he asignado el rol de **{profesion.value}**! 🛠️", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("No tengo permisos para darte roles.", ephemeral=True)


@bot.tree.command(name="añadir_crafteo", description="Añade una receta que sepas craftear usando el link de Wowhead Forever.")
async def añadir_crafteo(interaction: discord.Interaction, link: str):
    recipe_id = parse_wowhead_link(link)
    
    if not recipe_id:
        await interaction.response.send_message("❌ Link inválido. Debe contener `spell=` o `item=`.", ephemeral=True)
        return

    try:
        response = supabase.table('crafters').select('*').eq('recipe_id', recipe_id).eq('user_id', interaction.user.id).execute()
        if len(response.data) > 0:
            await interaction.response.send_message("Ya tenías esta receta registrada. ✅", ephemeral=True)
            return

        supabase.table('crafters').insert({
            'recipe_id': recipe_id,
            'user_id': interaction.user.id,
            'user_name': interaction.user.name
        }).execute()
        
        await interaction.response.send_message(f"¡Receta añadida a tu lista! (ID: `{recipe_id}`)", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error al guardar: {e}", ephemeral=True)


@bot.tree.command(name="pedir_crafteo", description="Pide un crafteo. El bot mencionará a todos los que tengan la receta.")
async def pedir_crafteo(interaction: discord.Interaction, link: str):
    user_id = interaction.user.id
    now = time.time()
    
    # Comprobamos el cooldown
    if user_id in cooldowns:
        time_left = cooldowns[user_id] - now
        if time_left > 0:
            mins = int(time_left // 60)
            secs = int(time_left % 60)
            await interaction.response.send_message(f"⏳ Para evitar spam, debes esperar {mins} min y {secs} secs para volver a pedir un crafteo.", ephemeral=True)
            return

    await interaction.response.defer()
    
    recipe_id = parse_wowhead_link(link)
    if not recipe_id:
        await interaction.followup.send("❌ Link inválido. Debe ser un link de Wowhead Forever.")
        return

    try:
        response = supabase.table('crafters').select('user_id, user_name').eq('recipe_id', recipe_id).execute()
        rows = response.data

        if not rows:
            await interaction.followup.send(f"Nadie en la guild tiene esta receta registrada. 😔\n*(ID: {recipe_id})*")
            cooldowns[user_id] = now + COOLDOWN_TIME
            return

        mentions = " ".join(f"<@{row['user_id']}>" for row in rows)
        
        message_content = (
            f"🔔 **¡Petición de Crafteo!** 🔔\n"
            f"{interaction.user.mention} necesita que alguien craftee este objeto:\n"
            f"🔗 {link}\n\n"
            f"**Crafteadores disponibles:** {mentions}\n"
            f"*(Usa el hilo de abajo para poneros de acuerdo con los materiales)*"
        )
        
        msg = await interaction.followup.send(message_content)
        thread_name = f"Crafteo: {recipe_id}"
        # Solución: crear el hilo desde el canal, no desde el mensaje
        thread = await interaction.channel.create_thread(name=thread_name, message=msg, reason="Comisión de crafteo")
        
        await thread.send(f"Hola {mentions}. Por favor, poneros de acuerdo con {interaction.user.mention} para gestionar la comisión. ¡Gracias!")
        # Guardamos el cooldown
        cooldowns[user_id] = now + COOLDOWN_TIME
    except Exception as e:
        await interaction.followup.send(f"❌ Ocurrió un error al buscar: {e}", ephemeral=True)

# ==========================================
# SERVIDOR WEB FALSO PARA RENDER (FREE TIER)
# ==========================================
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
