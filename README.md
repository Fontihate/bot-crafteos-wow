# 🛠️ Bot de Crafteos para WoWForever

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)
![Discord.py](https://img.shields.io/badge/Discord.py-2.0%2B-5865F2?style=for-the-badge&logo=discord&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)
![Render](https://img.shields.io/badge/Render-Hosted-black?style=for-the-badge&logo=render&logoColor=white)

Bot de Discord diseñado para gestionar y conectar crafteadores dentro de una guild de **World of Warcraft** (servidor *WoWForever*). 

Permite a los jugadores registrar las recetas que conocen y realiza un ping automático a todos los crafteadores disponibles cuando alguien necesita un objeto específico.

---

## ✨ Características Principales

* **Registro Dinámico:** Los usuarios añaden los crafteos que conocen mediante enlaces directos de **Wowhead**.
* **Filtro Inteligente de Enlaces:**
  * Acepta enlaces de `item=` de forma universal (evita problemas de idioma).
  * Solo acepta enlaces de `spell=` si corresponden a encantamientos (validando que contengan `enchant` o `encantar` en la URL).
* **Sistema Anti-Spam:** Cooldown de 30 minutos por usuario para prevenir el *flood* de peticiones.
* **Filtro Inter-Servidor:** Si el bot está en varios servidores de Discord, solo mencionará a los crafteadores presentes en el servidor donde se realiza la solicitud.
* **Base de Datos Persistente:** Integración con **Supabase (PostgreSQL)** para asegurar que los datos no se pierdan al reiniciar el bot.

---

## 🎮 Comandos Disponibles

| Comando | Descripción |
| :--- | :--- |
| `/añadir_crafteo link:[url]` | Registra una receta a tu nombre. *(Usa el enlace del objeto físico `item=`)*. |
| `/eliminar_crafteo link:[url]` | Elimina una receta de tu lista personal. |
| `/pedir_crafteo link:[url]` | Busca en la base de datos y menciona a los crafteadores disponibles en el servidor actual. |
