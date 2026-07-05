# This example requires the 'message_content' intent.

import discord
import io
import os
import re
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
hide_coords = True


def filter_log(text):
    blocked = []
    for line in text.split('\n'):
        lower = line.lower()
        if '/msg ' in lower or '/message ' in lower or '/tell ' in lower or '/w ' in lower or '/whisper ' in lower:
            continue
        if hide_coords:
            line = re.sub(r'at \([^)]*\)', 'at [FILTERED]', line)
            line = re.sub(r'position [^ \[]*\[[^\]]*\]', 'position [FILTERED]', line)
            line = re.sub(r'\[\[[^\]]*\]\]', '[FILTERED]', line)
        blocked.append(line)
    return '\n'.join(blocked)


async def monitor_loop(server_name, server_id, channel):
    last_log = ''
    was_running = True
    first_run = True
    while server_name in monitors:
        try:
            running = pufferpanel_api.get_server_status(server_id)
            if running:
                if not was_running:
                    await channel.send(':white_check_mark: **' + server_name + '** is back online, resuming logs.')
                    last_log = ''
                    was_running = True
                    first_run = True
                log_text = pufferpanel_api.get_server_logs(server_id)
                if log_text:
                    if first_run:
                        last_log = log_text
                        first_run = False
                        lines = [l for l in log_text.strip().split('\n') if l.strip()]
                        filtered = '\n'.join(lines)
                        filtered = filter_log(filtered)
                        filtered_lines = [l for l in filtered.split('\n') if l.strip()]
                        for i in range(0, len(filtered_lines), 20):
                            chunk = filtered_lines[i:i+20]
                            await channel.send('```\n' + '\n'.join(chunk) + '\n```')
                    elif len(log_text) > len(last_log):
                        new_text = log_text[len(last_log):]
                        last_log = log_text
                        lines = [l for l in new_text.split('\n') if l.strip()]
                        filtered = '\n'.join(lines)
                        filtered = filter_log(filtered)
                        filtered_lines = [l for l in filtered.split('\n') if l.strip()]
                        for i in range(0, len(filtered_lines), 20):
                            chunk = filtered_lines[i:i+20]
                            await channel.send('```\n' + '\n'.join(chunk) + '\n```')
            else:
                if was_running:
                    await channel.send(':octagonal_sign: **' + server_name + '** has been shut down, stopping monitor.')
                    del monitors[server_name]
                    return
                last_log = ''
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
    description='Shows the last 20 lines from a server')
@discord.app_commands.describe(server='The server to get logs for')
async def logs(interaction: discord.Interaction, server: Literal[tuple(servers)]):
    await interaction.response.defer(ephemeral=False)
    log_text = pufferpanel_api.get_server_logs(servers[server])
    if not log_text.strip():
        await interaction.followup.send('No logs found for ' + server, ephemeral=False)
        return
    filtered = filter_log(log_text)
    tail = filtered.strip().split('\n')[-20:]
    output = '\n'.join(tail)
    if len(output) > 1990:
        output = output[-1990:]
        output = '...' + output
    await interaction.followup.send('```\n' + output + '\n```', ephemeral=False)


@tree.command(
    name='logfile',
    description='Shows the last 20 lines from a specific log file (API)')
@discord.app_commands.describe(server='The server')
async def logfile(interaction: discord.Interaction, server: Literal[tuple(servers)]):
    await interaction.response.defer(ephemeral=False)
    log_text = pufferpanel_api.get_server_logs(servers[server])
    if not log_text.strip():
        await interaction.followup.send('No logs found for ' + server, ephemeral=False)
        return
    filtered = filter_log(log_text)
    file = discord.File(io.BytesIO(filtered.encode('utf-8')), filename=server + '_logs.txt')
    await interaction.followup.send(file=file, ephemeral=False)


@tree.command(
    name='getlogs',
    description='Downloads the current console output as a file')
@discord.app_commands.describe(server='The server to get logs for')
async def getlogs(interaction: discord.Interaction, server: Literal[tuple(servers)]):
    await interaction.response.defer(ephemeral=False)
    log_text = pufferpanel_api.get_server_logs(servers[server])
    if not log_text.strip():
        await interaction.followup.send('No logs found for ' + server, ephemeral=False)
        return
    filtered = filter_log(log_text)
    file = discord.File(io.BytesIO(filtered.encode('utf-8')), filename=server + '_console.log')
    await interaction.followup.send(server + ' console log:', file=file, ephemeral=False)


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


@tree.command(
    name='hidecords',
    description='Toggles hiding player coordinates in log output')
async def hidecords(interaction: discord.Interaction):
    global hide_coords
    hide_coords = not hide_coords
    if hide_coords:
        await interaction.response.send_message(':shield: Coordinate filtering is now **ON**.', ephemeral=False)
    else:
        await interaction.response.send_message(':warning: Coordinate filtering is now **OFF**.', ephemeral=False)


@client.event
async def on_ready():
    old = await client.http.get_global_commands(client.user.id)
    print(f'Deleting {len(old)} old commands')
    for cmd in old:
        await client.http.delete_global_command(client.user.id, int(cmd['id']))
    synced = await tree.sync()
    print(f'We have logged in as {client.user}, synced {len(synced)} commands: {[c.name for c in synced]}')


client.run(token)
