# This example requires the 'message_content' intent.

import discord
import io
import os
import asyncio
import pufferpanel_api
from dotenv import load_dotenv
from typing import Literal

load_dotenv()
token = os.getenv('BOT_TOKEN')

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

servers = pufferpanel_api.get_servers()

monitors = {}


async def monitor_loop(server_name, server_id, channel):
    buffer = []
    was_running = True
    while server_name in monitors:
        try:
            running = pufferpanel_api.get_server_status(server_id)
            if running:
                if not was_running:
                    await channel.send(':white_check_mark: **' + server_name + '** is back online, resuming logs.')
                    buffer = []
                    was_running = True
                log_text = pufferpanel_api.get_server_logs(server_id)
                if log_text:
                    lines = log_text.strip().split('\n')
                    new_lines = lines[len(buffer):]
                    buffer = lines
                    batch = [l for l in new_lines if l.strip()]
                    for i in range(0, len(batch), 20):
                        chunk = batch[i:i+20]
                        await channel.send('```\n' + '\n'.join(chunk) + '\n```')
            else:
                if was_running:
                    await channel.send(':octagonal_sign: **' + server_name + '** has been shut down, stopping monitor.')
                    del monitors[server_name]
                    return
                buffer = []
        except Exception as e:
            print(f'Monitor error for {server_name}: {e}')
        await asyncio.sleep(1)


@tree.command(
    name='start',
    description='Starts a server')
@discord.app_commands.describe(server='The server to start')
async def startServer(interaction: discord.Interaction, server: Literal[tuple(servers)]):
    if not pufferpanel_api.get_server_status(servers[server]):
        await interaction.response.send_message('Starting ' + server + '!', ephemeral=False)
        pufferpanel_api.start_server(servers[server])
    else:
        await interaction.response.send_message(server + ' is already running!', ephemeral=False)


@tree.command(
    name='stop',
    description='Stops a server')
@discord.app_commands.describe(server='The server to stop')
async def stopServer(interaction: discord.Interaction, server: Literal[tuple(servers)]):
    if pufferpanel_api.get_server_status(servers[server]):
        await interaction.response.send_message('Stopping ' + server + '!', ephemeral=False)
        pufferpanel_api.stop_server(servers[server])
    else:
        await interaction.response.send_message(server + ' is already stopped!', ephemeral=False)


@tree.command(
    name='servers',
    description='Lists all servers')
async def listServers(interaction: discord.Interaction):
    global servers
    servers = pufferpanel_api.get_servers()
    serverstring = ""
    for server in servers:
        if pufferpanel_api.get_server_status(servers[server]):
            serverstring += ':white_check_mark: ' + server + '\n'
        else:
            serverstring += ':octagonal_sign: ' + server + '\n'

    await interaction.response.send_message(serverstring, ephemeral=False)


@tree.command(
    name='logs',
    description='Downloads the latest log from a server')
@discord.app_commands.describe(server='The server to get logs for')
async def logs(interaction: discord.Interaction, server: Literal[tuple(servers)]):
    await interaction.response.defer(ephemeral=False)
    log_text = pufferpanel_api.get_server_logs(servers[server])
    if not log_text.strip():
        await interaction.followup.send('No logs found for ' + server, ephemeral=False)
        return
    tail = log_text.strip().split('\n')[-20:]
    output = '\n'.join(tail)
    if len(output) > 1990:
        output = output[-1990:]
        output = '...' + output
    await interaction.followup.send('```\n' + output + '\n```', ephemeral=False)


@tree.command(
    name='monitor',
    description='Starts live log monitoring in this channel')
@discord.app_commands.describe(server='The server to monitor')
async def monitor(interaction: discord.Interaction, server: Literal[tuple(servers)]):
    if server in monitors:
        await interaction.response.send_message(server + ' is already being monitored!', ephemeral=False)
        return
    monitors[server] = True
    await interaction.response.send_message('Started monitoring ' + server + ' logs here.', ephemeral=False)
    client.loop.create_task(monitor_loop(server, servers[server], interaction.channel))


@tree.command(
    name='unmonitor',
    description='Stops live log monitoring')
@discord.app_commands.describe(server='The server to stop monitoring')
async def unmonitor(interaction: discord.Interaction, server: Literal[tuple(servers)]):
    if server not in monitors:
        await interaction.response.send_message(server + ' is not being monitored.', ephemeral=False)
        return
    del monitors[server]
    await interaction.response.send_message('Stopped monitoring ' + server + ' logs.', ephemeral=False)


@client.event
async def on_ready():
    old = await client.http.get_global_commands(client.user.id)
    print(f'Deleting {len(old)} old commands')
    for cmd in old:
        await client.http.delete_global_command(client.user.id, int(cmd['id']))
    synced = await tree.sync()
    print(f'We have logged in as {client.user}, synced {len(synced)} commands: {[c.name for c in synced]}')


client.run(token)
