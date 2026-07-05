# This example requires the 'message_content' intent.

import discord
import io
import os
import gzip
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
servers_dir = os.getenv('SERVERS_DIR', '/home/blake7/game_servers/servers')

monitors = {}
hide_coords = True


def get_log_files(server_id):
    logs_path = os.path.join(servers_dir, server_id, 'logs')
    if not os.path.isdir(logs_path):
        return []
    files = []
    for f in sorted(os.listdir(logs_path), reverse=True):
        if f.endswith('.log') or f.endswith('.gz'):
            files.append(f)
    return files


def read_log_file(server_id, filename):
    path = os.path.join(servers_dir, server_id, 'logs', filename)
    if not os.path.exists(path):
        return ''
    if filename.endswith('.gz'):
        with gzip.open(path, 'rt', errors='replace') as f:
            return f.read()
    with open(path, 'r', errors='replace') as f:
        return f.read()


def read_log_tail(server_id, filename, lines=20):
    path = os.path.join(servers_dir, server_id, 'logs', filename)
    if not os.path.exists(path):
        return ''
    if filename.endswith('.gz'):
        with gzip.open(path, 'rt', errors='replace') as f:
            all_lines = f.readlines()
    else:
        with open(path, 'r', errors='replace') as f:
            all_lines = f.readlines()
    return ''.join(all_lines[-lines:])


def filter_log(text):
    blocked = []
    for line in text.split('\n'):
        lower = line.lower()
        if '/msg ' in lower or '/message ' in lower or '/tell ' in lower or '/w ' in lower or '/whisper ' in lower:
            continue
        if hide_coords:
            import re
            line = re.sub(r'at \([^)]*\)', 'at [FILTERED]', line)
            line = re.sub(r'position [^ \[]*\[[^\]]*\]', 'position [FILTERED]', line)
            line = re.sub(r'\[\[[^\]]*\]\]', '[FILTERED]', line)
        blocked.append(line)
    return '\n'.join(blocked)


def read_latest_log_tail(server_id, lines=40):
    path = os.path.join(servers_dir, server_id, 'logs', 'latest.log')
    if not os.path.exists(path):
        return ''
    with open(path, 'r', errors='replace') as f:
        all_lines = f.readlines()
    return ''.join(all_lines[-lines:])


async def monitor_loop(server_name, server_id, channel):
    path = os.path.join(servers_dir, server_id, 'logs', 'latest.log')
    last_pos = 0
    was_running = True
    if os.path.exists(path):
        with open(path, 'r', errors='replace') as f:
            f.seek(0, 2)
            last_pos = f.tell()
    while server_name in monitors:
        try:
            running = pufferpanel_api.get_server_status(server_id)
            if running:
                if not was_running:
                    await channel.send(':white_check_mark: **' + server_name + '** is back online, resuming logs.')
                    if os.path.exists(path):
                        with open(path, 'r', errors='replace') as f:
                            f.seek(0, 2)
                            last_pos = f.tell()
                    was_running = True
                if os.path.exists(path):
                    with open(path, 'r', errors='replace') as f:
                        f.seek(last_pos)
                        new_data = f.read()
                        last_pos = f.tell()
                    if new_data:
                        filtered = filter_log(new_data)
                        lines = [l for l in filtered.split('\n') if l.strip()]
                        for i in range(0, len(lines), 20):
                            chunk = lines[i:i+20]
                            await channel.send('```\n' + '\n'.join(chunk) + '\n```')
            else:
                if was_running:
                    await channel.send(':octagonal_sign: **' + server_name + '** has been shut down, stopping monitor.')
                    del monitors[server_name]
                    return
                last_pos = 0
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
    log_text = read_latest_log_tail(servers[server])
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
    description='Lists log files for a server')
@discord.app_commands.describe(server='The server to list logs for')
async def logfile(interaction: discord.Interaction, server: Literal[tuple(servers)]):
    await interaction.response.defer(ephemeral=False)
    files = get_log_files(servers[server])
    if not files:
        await interaction.followup.send('No log files found for ' + server, ephemeral=False)
        return
    view = LogFileView(server, servers[server], files)
    await interaction.followup.send('Select a log file for **' + server + '**:', view=view, ephemeral=False)


class LogSelect(discord.ui.Select):
    def __init__(self, server_name, server_id, files):
        options = []
        for f in files[:25]:
            size = os.path.getsize(os.path.join(servers_dir, server_id, 'logs', f))
            if size > 1024 * 1024:
                size_str = f'{size / (1024*1024):.1f} MB'
            elif size > 1024:
                size_str = f'{size / 1024:.1f} KB'
            else:
                size_str = f'{size} B'
            label = f'{f} ({size_str})'
            if len(label) > 100:
                label = label[:97] + '...'
            options.append(discord.SelectOption(label=label, value=f))
        super().__init__(placeholder='Choose a log file...', options=options)
        self.server_name = server_name
        self.server_id = server_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        text = read_log_file(self.server_id, self.values[0])
        if not text.strip():
            await interaction.followup.send('File is empty.', ephemeral=False)
            return
        filtered = filter_log(text)
        tail = filtered.strip().split('\n')[-20:]
        output = '\n'.join(tail)
        if len(output) > 1990:
            output = output[-1990:]
            output = '...' + output
        file = discord.File(io.BytesIO(filtered.encode('utf-8')), filename=self.values[0])
        await interaction.followup.send('**' + self.values[0] + '** (last 20 lines):', file=file, content='```\n' + output + '\n```', ephemeral=False)


class LogFileView(discord.ui.View):
    def __init__(self, server_name, server_id, files):
        super().__init__(timeout=60)
        self.add_item(LogSelect(server_name, server_id, files))


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
