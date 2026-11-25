"""Discord via `discord.py` (gateway — conexão de saída, sem porta aberta).

Responde só a DM ou a menção ao bot. Intents mínimos (`message_content` para ler o
texto da DM/menção). Sem a lib instalada a ponte do Discord fica desligada com aviso.
"""
import asyncio

from core.logger import log


def available():
    try:
        import discord  # noqa: F401
        return True
    except ImportError:
        return False


def clean_text(content, bot_id):
    """Tira a menção ao bot do começo da mensagem."""
    for mention in (f"<@{bot_id}>", f"<@!{bot_id}>"):
        content = content.replace(mention, "")
    return content.strip()


def run(token, handler, stop_event):
    """Bloqueante (thread daemon do messenger). `handler(canal, user_id, texto) -> [respostas]`."""
    try:
        import discord
    except ImportError:
        log.warning("[DISCORD] discord.py não instalado: ponte do Discord desligada.")
        return
    intents = discord.Intents.none()
    intents.guilds = intents.dm_messages = intents.guild_messages = intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        log.info(f"[DISCORD] Ponte no ar como {client.user}.")

    @client.event
    async def on_message(message):
        if message.author.bot or message.author == client.user:
            return
        is_dm = message.guild is None
        if not is_dm and client.user not in message.mentions:
            return
        text = clean_text(message.content or "", client.user.id)
        loop = asyncio.get_running_loop()
        async with message.channel.typing():
            try:
                replies = await loop.run_in_executor(None, handler, "discord", str(message.author.id), text)
            except Exception as e:
                log.error(f"[DISCORD] Tratamento falhou: {e}")
                replies = ["Algo deu errado do meu lado, Senhor."]
        for part in replies or []:
            await message.channel.send(part)

    async def main():
        async with client:
            starter = asyncio.create_task(client.start(token))
            while not stop_event.is_set() and not starter.done():
                await asyncio.sleep(1)
            if not starter.done():
                await client.close()
            elif starter.exception():
                log.warning(f"[DISCORD] Conexão encerrada: {type(starter.exception()).__name__}")

    try:
        asyncio.run(main())
    except Exception as e:
        log.warning(f"[DISCORD] Ponte parou: {type(e).__name__}")
