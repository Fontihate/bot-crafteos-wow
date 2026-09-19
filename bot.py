import discord
from discord.ext import commands
from discord import app_commands
import re
import os
import time
import requests
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
# FUNCIONES AUXILIARES (SCRAPEO WOWHEAD)
# ==========================================
def get_recipe_ids(url: str) -> tuple:
    match = re.search(r'wowhead\.com/forever(?:/\w+)?/(spell|item)=(\d+)', url)
    if not match:
        return None, None
    
    url_type = match.group(1)
    url_id = match.group(2)
    
    clean_url = f"https://www.wowhead.com/forever/{url_type}={url_id}"
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(clean_url, headers=headers, timeout=5)
        html = response.text
        
        spell_id = None
        item_id = None
        
        if url_type == 'spell':
            spell_id = url_id
            create_match = re.search(r'Create Item', html, re.IGNORECASE)
            if create_match:
                start_pos = create_match.end()
                item_match = re.search(r'item=(\d+)', html[start_pos:])
                if item_match:
                    item_id = item_match.group(1)
            
            if not item_id:
                if 'enchant' in html.lower():
                    pass
                else:
                    return "SPELL_NO_ENCHANT", None
                    
        elif url_type == 'item':
            item_id = url_id
            created_match = re.search(r'Created by', html, re.IGNORECASE)
            if created_match:
                start_pos = created_match.end()
                spell_match = re.search(r'spell=(\d+)', html[start_pos:])
                if spell_match:
                    spell_id = spell_match.group(1)
                
        return spell_id, item_id
        
    except Exception as e:
        print(f"Error en scrapeo HTML: {e}")
        return None, None

# ==========================================
# CONFIGURACIÓN DEL BOT
# ==========================================
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

cooldowns = {}
COOLDOWN_TIME = 1800

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

@bot.tree.command(name="añadir_crafteo", description="Añade una receta que sepas craftear usando el link de Wowhead Forever.")
async def añadir_crafteo(interaction: discord.Interaction, link: str):
    await interaction.response.defer(ephemeral=True)
    
    spell_id, item_id = get_recipe_ids(link)
    
    if spell_id == "SPELL_NO_ENCHANT":
        await interaction.followup.send("❌ Has puesto un link de `spell=` de algo que no es un Enchant. Para recetas normales busca el **objeto físico** en Wowhead y usa su link.", ephemeral=True)
        return
    if not spell_id and not item_id:
        await interaction.followup.send("❌ Link inválido. Asegúrate de copiar un link de Wowhead Forever.", ephemeral=True)
        return

    recipe_id = item_id if item_id else spell_id

    try:
        response = supabase.table('crafters').select('*').eq('recipe_id', recipe_id).eq('user_id', interaction.user.id).execute()
        if len(response.data) > 0:
            await interaction.followup.send("Ya tenías esta receta registrada. ✅", ephemeral=True)
            return

        supabase.table('crafters').insert({
            'recipe_id': recipe_id,
            'user_id': interaction.user.id,
            'user_name': interaction.user.name
        }).execute()
        
        msg = "¡Receta añadida a tu lista global! ✅\n"
        if spell_id and item_id:
            msg += f"Spell ID: `{spell_id}` | Item ID: `{item_id}`"
        elif spell_id and not item_id:
            msg += f"Spell ID (Enchant): `{spell_id}`"
        elif item_id and not spell_id:
            msg += f"Item ID: `{item_id}` (No se encontró el Spell de origen)"
            
        await interaction.followup.send(msg, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error al guardar: {e}", ephemeral=True)


@bot.tree.command(name="eliminar_crafteo", description="Elimina una receta de tu lista si te equivocaste al ponerla.")
async def eliminar_crafteo(interaction: discord.Interaction, link: str):
    await interaction.response.defer(ephemeral=True)
    
    spell_id, item_id = get_recipe_ids(link)
    if not spell_id and not item_id:
        await interaction.followup.send("❌ Link inválido.", ephemeral=True)
        return

    recipe_id = item_id if item_id else spell_id

    try:
        response = supabase.table('crafters').delete().eq('recipe_id', recipe_id).eq('user_id', interaction.user.id).execute()
        if len(response.data) > 0:
            await interaction.followup.send(f"🗑️ Receta eliminada de tu lista correctamente.", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ No tenías esa receta registrada a tu nombre.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error al borrar: {e}", ephemeral=True)


@bot.tree.command(name="pedir_crafteo", description="Pide un crafteo. El bot mencionará a quienes sepan hacerlo y estén en este Discord.")
async def pedir_crafteo(interaction: discord.Interaction, link: str):
    user_id = interaction.user.id
    now = time.time()
    
    if user_id in cooldowns:
        time_left = cooldowns[user_id] - now
        if time_left > 0:
            mins = int(time_left // 60)
            secs = int(time_left % 60)
            await interaction.response.send_message(f"⏳ Para evitar spam, debes esperar {mins} min y {secs} secs.", ephemeral=True)
            return

    await interaction.response.defer()
    
    spell_id, item_id = get_recipe_ids(link)
    if not spell_id and not item_id:
        await interaction.followup.send("❌ Link inválido.", ephemeral=True)
        return

    recipe_id = item_id if item_id else spell_id

    try:
        response = supabase.table('crafters').select('user_id, user_name').eq('recipe_id', recipe_id).execute()
        rows = response.data

        if not rows:
            await interaction.followup.send(f"Nadie sabe craftear esto todavía. 😔\n*(ID: {recipe_id})*")
            cooldowns[user_id] = now + COOLDOWN_TIME
            return

        mentions = []
        for row in rows:
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
# SERVIDOR WEB FALSO PARA RENDER
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

TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN is None:
    print("ERROR CRÍTICO: No se ha encontrado el token de Discord.")
else:
    keep_alive()
    bot.run(TOKEN)
