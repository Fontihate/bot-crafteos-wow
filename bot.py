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
def get_recipe_id(url: str) -> str:
    """Filtra el link: Acepta ITEM siempre. Acepta SPELL solo si es un encanto."""
    url = url.rstrip('/')
    last_part = url.split('/')[-1].lower()
    
    match = re.search(r'item=(\d+)', url)
    if match:
        return match.group(1)
        
    match = re.search(r'spell=(\d+)', url)
    if match:
        if 'enchant' in last_part or 'encantar' in last_part:
            return match.group(1)
        return "SPELL_NO_ENCHANT"
        
    return None

# ==========================================
# CONFIGURACIÓN DEL BOT
# ==========================================
intents = discord.Intents.default()
intents.members = True # VITAL para poder comprobar si alguien está en un servidor

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

@bot.tree.command(name="añadir_crafteo", description="Añade una receta que sepas craftear usando el link del objeto (item=) de Wowhead Forever.")
async def añadir_crafteo(interaction: discord.Interaction, link: str):
    recipe_id = get_recipe_id(link)
    
    if recipe_id == "SPELL_NO_ENCHANT":
        await interaction.response.send_message("❌ Has puesto un link de `spell=`. Para recetas normales, busca en Wowhead el **objeto físico** y usa su link (el que lleva `item=`).", ephemeral=True)
        return
    elif not recipe_id:
        await interaction.response.send_message("❌ Link inválido. Asegúrate de copiar un link de Wowhead Forever que contenga `item=`.", ephemeral=True)
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
        
        await interaction.response.send_message(f"¡Receta añadida a tu lista global! (ID: `{recipe_id}`)", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error al guardar: {e}", ephemeral=True)


@bot.tree.command(name="eliminar_crafteo", description="Elimina una receta de tu lista si te equivocaste al ponerla.")
async def eliminar_crafteo(interaction: discord.Interaction, link: str):
    recipe_id = get_recipe_id(link)
    
    if recipe_id == "SPELL_NO_ENCHANT":
        await interaction.response.send_message("❌ Has puesto un link de `spell=`. Para recetas normales usa el link del objeto (`item=`).", ephemeral=True)
        return
    elif not recipe_id:
        await interaction.response.send_message("❌ Link inválido. Asegúrate de copiar un link de Wowhead Forever que contenga `item=`.", ephemeral=True)
        return

    try:
        response = supabase.table('crafters').delete().eq('recipe_id', recipe_id).eq('user_id', interaction.user.id).execute()
        
        if len(response.data) > 0:
            await interaction.response.send_message(f"🗑️ Receta eliminada de tu lista correctamente. (ID: `{recipe_id}`)", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ No tenías esa receta registrada a tu nombre, así que no he borrado nada.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error al borrar: {e}", ephemeral=True)


@bot.tree.command(name="pedir_crafteo", description="Pide un crafteo. El bot mencionará a quienes sepan hacerlo y estén en este Discord.")
async def pedir_crafteo(interaction: discord.Interaction, link: str):
    user_id = interaction.user.id
    now = time.time()
    
    if user_id in cooldowns:
        time_left = cooldowns[user_id] - now
        if time_left > 0:
            mins = int(time_left // 60)
            secs = int(time_left % 60)
            await interaction.response.send_message(f"⏳ Para evitar spam, debes esperar {mins} min y {secs} secs para volver a pedir un crafteo.", ephemeral=True)
            return

    await interaction.response.defer()
    
    recipe_id = get_recipe_id(link)
    if recipe_id == "SPELL_NO_ENCHANT":
        await interaction.followup.send("❌ Has puesto un link de `spell=`. Para pedir recetas normales, usa el link del objeto (`item=`).", ephemeral=True)
        return
    elif not recipe_id:
        await interaction.followup.send("❌ Link inválido. Asegúrate de copiar un link de Wowhead Forever que contenga `item=`.", ephemeral=True)
        return

    try:
        # Sacamos a todos los que tienen la receta en la BD global
        response = supabase.table('crafters').select('user_id, user_name').eq('recipe_id', recipe_id).execute()
        rows = response.data

        if not rows:
            await interaction.followup.send(f"Nadie sabe craftear esto todavía. 😔\n*(ID: {recipe_id})*")
            cooldowns[user_id] = now + COOLDOWN_TIME
            return

        # FILTRO INTER-SERVIDOR: Comprobamos quiénes de la lista están en ESTE Discord
        mentions = []
        for row in rows:
            # interaction.guild.get_member devuelve None si el usuario no está en este servidor
            if interaction.guild.get_member(row['user_id']):
                mentions.append(f"<@{row['user_id']}>")

        if not mentions:
            await interaction.followup.send("Hay gente que sabe craftear esto, pero ninguno está en este servidor de Discord. 😔")
            cooldowns[user_id] = now + COOLDOWN_TIME
            return

        mentions_str = " ".join(mentions)
        
        message_content = (
            f"🔔 **¡Petición de Crafteo!** 🔔\n"
            f"{interaction.user.mention} necesita que alguien craftee este objeto:\n"
            f"🔗 {link}\n\n"
            f"**Crafteadores disponibles aquí:** {mentions_str}\n"
            f"*(Poneos de acuerdo por mensaje privado o en el canal)*"
        )
        
        await interaction.followup.send(message_content)
        
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
