import discord
from discord.ext import commands, tasks
from discord.utils import get
import datetime
import html
import io
import asyncio
import os

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- CONFIG ---------------- #
CONFIG = {
    "support_panel_channel": 1474229747079844014,
    "support_category": 1484880203749785691,
    "partnership_category": 1484880306484936816,
    "order_panel_channel": 1474460217877205217,
    "order_unclaimed_category": 1485800684740804709,
    "order_claimed_category": 1485800916199280801,
    "log_channel": 1475295896118755400,
    "vip_order_roles": [1478947007979851908],
    "staff_order_roles": [
        1474547037344370952,
        1474546634968006827,
        1474546294990176471
    ],
    "staff_permission_role": 1474517835261804656,
    "order_view_roles_after_claim": [
        1474517571129839787,
        1474532331028090992
    ]
}

ticket_counter = 0
claimed_tickets = {}
ticket_open_times = {}
last_message_time = {}
staff_request_sent_channels = set()

# ---------------- HELPERS ---------------- #
def generate_ticket_name(user, type_):
    global ticket_counter
    ticket_counter += 1
    if type_ == "support":
        return f"support-{user.name}-{ticket_counter}"
    if type_ == "partnership":
        return f"partnership-{user.name}-{ticket_counter}"
    if type_ == "order_unclaimed":
        return f"unclaimed-{user.name}"
    if type_ == "order_claimed":
        return f"{user.name}-claimed"
    return f"ticket-{user.name}-{ticket_counter}"

def max_order_tickets(user):
    if any(r.id in CONFIG["vip_order_roles"] for r in user.roles):
        return 6
    elif any(r.id in CONFIG["staff_order_roles"] for r in user.roles):
        return 5
    else:
        return 3

def count_user_order_tickets(guild, user):
    count = 0
    for channel in guild.text_channels:
        name = channel.name.lower()
        if user.name.lower() in name and ("unclaimed" in name or "claimed" in name):
            count += 1
    return count

def get_ticket_owner(channel):
    for member in channel.members:
        if not member.bot:
            return member
    return None

# ---------------- TRANSCRIPTS ---------------- #
async def create_transcript(channel, claimed_by=None, ticket_user=None, category_name=None):
    messages = []
    async for msg in channel.history(limit=None, oldest_first=True):
        messages.append(msg)
    opened_at = channel.created_at.strftime("%Y-%m-%d %H:%M:%S")
    html_content = f"<html><body><h2>Ticket Transcript</h2><p>User: {ticket_user.name if ticket_user else 'Unknown'}<br>Category: {category_name if category_name else 'Unknown'}<br>Handled by: {claimed_by if claimed_by else 'Unclaimed'}<br>Opened: {opened_at}</p>"
    for msg in messages:
        content = html.escape(msg.content)
        html_content += f"<p><b>{msg.author}:</b> {content}</p>"
    html_content += "</body></html>"
    return html_content

async def send_transcript(channel, user):
    claimed_by = claimed_tickets.get(channel.id)
    html_content = await create_transcript(channel, claimed_by=claimed_by, ticket_user=get_ticket_owner(channel), category_name=channel.category.name if channel.category else "None")
    file = discord.File(io.BytesIO(html_content.encode()), filename="transcript.html")
    log_channel = bot.get_channel(CONFIG["log_channel"])
    embed = discord.Embed(title="🎟️ Ticket Closed", color=0xF8C8DC)
    embed.add_field(name="User", value=user.mention if user else "Unknown")
    embed.add_field(name="Channel", value=f"#{channel.name}")
    embed.add_field(name="Handled by", value=f"<@{claimed_by}>" if claimed_by else "Unclaimed")
    await log_channel.send(embed=embed, file=file)
    try:
        if user:
            await user.send("💖 Your ticket has been closed.", file=file)
    except: pass

# ---------------- PANEL COMMAND ---------------- #
@bot.command()
@commands.has_permissions(administrator=True)
async def panel(ctx, type_: str):
    if type_ == "main":
        embed = discord.Embed(
            description=(
                "## ⠀✿⠀⠀ticket lounge⠀⠀♰\n\n"
                "_ _\n\n"
                "__Guidelines__\n\n"
                "<:emoji_39:1483249281237254326> open only if necessary\n"
                "<:emoji_39:1483249281237254326> select the correct ticket\n"
                "<:emoji_39:1483249281237254326> empty / inactive = closed\n"
                "<:emoji_39:1483249281237254326> be patient + respectful\n\n"
                "_ _\n\n"
                "__Support__\n\n"
                "<:emoji_39:1483249281237254326> help + questions\n"
                "<:emoji_39:1483249281237254326> reports (members / staff)\n"
                "<:emoji_39:1483249281237254326> purchases / subscriptions\n"
                "<:emoji_39:1483249281237254326> giveaways / rewards\n"
                "<:emoji_39:1483249281237254326> server issues\n\n"
                "_ _\n\n"
                "__Partnership__\n\n"
                "♰ server partnerships\n"
                "♰ rep changes / inquiries\n\n"
                "_ _\n\n"
                "__note__\n\n"
                "<:emoji_39:1483249281237254326> read info before opening\n"
                "<:emoji_39:1483249281237254326> no trolling / spam\n\n"
                "_ _\n\n"
                "Tap below to open a ticket"
            ),
            color=0x1b1c23
        )
        embed.set_footer(text="Cottage Tickets ✧")

        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            label="Support",
            emoji="<:CC_Ticket:1478922207110631446>",
            style=discord.ButtonStyle.secondary,
            custom_id="support"
        ))
        view.add_item(discord.ui.Button(
            label="Partnership",
            emoji="<:CC_Ticket:1478922207110631446>",
            style=discord.ButtonStyle.secondary,
            custom_id="partnership"
        ))

        panel_channel = bot.get_channel(CONFIG["support_panel_channel"])
        await panel_channel.send(embed=embed, view=view)
        await ctx.message.delete()
    elif type_ == "order":
        embed = discord.Embed(
            title="🛒 Order Tickets",
            description="Click below to open an order ticket ✧",
            color=0x1b1c23
        )
        embed.set_footer(text="Cottage Tickets ✧")
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="🛒 Order", custom_id="order", style=discord.ButtonStyle.secondary))
        order_channel = bot.get_channel(CONFIG["order_panel_channel"])
        await order_channel.send(embed=embed, view=view)
        await ctx.message.delete()

# ---------------- INTERACTIONS ---------------- #
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not interaction.data: return
    custom_id = interaction.data.get("custom_id")
    user = interaction.user
    guild = interaction.guild
    if not guild: return
    staff_role = guild.get_role(CONFIG["staff_permission_role"])

    # ---------------- ORDER ---------------- #
    if custom_id == "order":
        existing = count_user_order_tickets(guild, user)
        limit = max_order_tickets(user)
        if existing >= limit:
            await interaction.response.send_message(f"❌ You reached your limit ({existing}/{limit})", ephemeral=True)
            return

        category = bot.get_channel(CONFIG["order_unclaimed_category"])
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        channel = await guild.create_text_channel(generate_ticket_name(user,"order_unclaimed"), category=category, overwrites=overwrites)
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="🔒 Close", custom_id="close"))
        view.add_item(discord.ui.Button(label="📝 Claim", custom_id="claim"))
        await channel.send(f"{user.mention}", embed=discord.Embed(title="🛒 Order Ticket", description="Please wait for a chef ✧", color=0xF8C8DC), view=view)
        ticket_open_times[channel.id] = datetime.datetime.utcnow()
        await interaction.response.send_message(f"Created: {channel.mention}", ephemeral=True)

    # ---------------- CLAIM ---------------- #
    elif custom_id == "claim":
        channel = interaction.channel
        owner = get_ticket_owner(channel)
        if channel.id in claimed_tickets:
            await interaction.response.send_message("❌ Already claimed", ephemeral=True)
            return
        claimed_tickets[channel.id] = user.id

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            owner: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        for role_id in CONFIG["order_view_roles_after_claim"]:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        await channel.edit(name=generate_ticket_name(owner,"order_claimed"), category=bot.get_channel(CONFIG["order_claimed_category"]), overwrites=overwrites, topic=f"Claimed by {user.name}")
        embed = discord.Embed(description=f"✧ This order is now being handled by {user.mention}\nPlease wait while your request is completed ♡", color=0xF8C8DC)
        await channel.send(embed=embed)
        await interaction.response.send_message("✅ Claimed", ephemeral=True)

    # ---------------- CLOSE ---------------- #
    elif custom_id == "close":
        channel = interaction.channel
        owner = get_ticket_owner(channel)
        is_staff = staff_role in user.roles if staff_role else False
        is_owner = owner and user.id == owner.id
        if not is_staff and not is_owner:
            await interaction.response.send_message("❌ Only staff or ticket owner can close.", ephemeral=True)
            return
        await interaction.response.send_message("🔒 Closing ticket...", ephemeral=True)
        try:
            await send_transcript(channel, owner)
        except Exception as e:
            print(f"Transcript error: {e}")
        await channel.delete()

# ---------------- MESSAGE TRACK ---------------- #
@bot.event
async def on_message(message):
    if message.author.bot: return
    name = message.channel.name.lower()
    if name.startswith(("support-","partnership-","unclaimed-","❗️unclaimed-","❕unclaimed-","order-")):
        last_message_time[message.channel.id] = datetime.datetime.utcnow()
    await bot.process_commands(message)

# ---------------- INACTIVITY ---------------- #
class StaffInactivityView(discord.ui.View):
    def __init__(self, channel_id):
        super().__init__(timeout=2*3600)
        self.channel_id = channel_id

    @discord.ui.button(label="✅ Close Ticket", style=discord.ButtonStyle.danger)
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = bot.get_channel(self.channel_id)
        owner = get_ticket_owner(channel)
        await send_transcript(channel, owner)
        await channel.delete()
        self.stop()

    @discord.ui.button(label="🕒 Keep Open", style=discord.ButtonStyle.secondary)
    async def keep_open(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Ticket will remain open.", ephemeral=True)
        self.stop()

async def ticket_inactivity_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.datetime.utcnow()
        for channel_id, last_time in list(last_message_time.items()):
            channel = bot.get_channel(channel_id)
            if not channel:
                last_message_time.pop(channel_id)
                continue
            delta = (now - last_time).total_seconds()
            if delta >= 86400 and channel_id not in staff_request_sent_channels:
                staff_request_sent_channels.add(channel_id)
                staff_mention = f"<@&{CONFIG['staff_permission_role']}>"
                embed = discord.Embed(title="⚠️ Ticket Inactivity Notice", description=f"{staff_mention}\nThis ticket has been inactive for 24 hours. Close?", color=0xF8C8DC)
                view = StaffInactivityView(channel_id)
                await channel.send(embed=embed, view=view)
            elif delta >= 93600:
                owner = get_ticket_owner(channel)
                await send_transcript(channel, owner)
                await channel.delete()
                last_message_time.pop(channel_id)
                staff_request_sent_channels.discard(channel_id)
        await asyncio.sleep(300)

# ---------------- READY ---------------- #
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.tree.sync()
    bot.loop.create_task(ticket_inactivity_loop())

# ---------------- RUN ---------------- #
bot.run(os.getenv("TOKEN"))