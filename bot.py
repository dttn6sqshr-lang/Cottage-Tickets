import discord
from discord.ext import commands, tasks
from discord.utils import get
import datetime
import html
import io
import asyncio
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler


# ---------------- KEEP ALIVE ---------------- #
class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

    def log_message(self, format, *args):
        pass


def keep_alive():
    server = HTTPServer(("0.0.0.0", 5000), KeepAliveHandler)
    server.serve_forever()


threading.Thread(target=keep_alive, daemon=True).start()

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
    "log_channel": 1485800916199280801,
    "vip_order_roles": [1478947007979851908],
    "staff_order_roles": [
        1474547037344370952,
        1474546634968006827,
        1474546294990176471
    ],
    "staff_permission_role": 1474517835261804656
}

ticket_counter = 0
claimed_tickets = {}
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
        if any(r.id in CONFIG["vip_order_roles"] for r in user.roles):
            return f"❗️unclaimed-{user.name}"
        elif any(r.id in CONFIG["staff_order_roles"] for r in user.roles):
            return f"❕unclaimed-{user.name}"
        else:
            return f"unclaimed-{user.name}"
    if type_ == "order_claimed":
        return f"{user.name}-claimed-chef"
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
    html_content = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ background-color: #fff5e1; font-family: 'Segoe UI', sans-serif; color: #5a4a42; padding: 20px; }}
            .container {{ max-width: 850px; margin: auto; background: #ffffff; border-radius: 15px; padding: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.08); }}
            .header {{ text-align: center; margin-bottom: 15px; }}
            .logo {{ width: 80px; margin-bottom: 10px; }}
            .title {{ color: #f8c8dc; font-size: 24px; margin-bottom: 5px; }}
            .info-card {{ background: #fff0f5; padding: 15px; border-radius: 12px; margin-bottom: 20px; }}
            .info-card b {{ color: #d48aa3; }}
            .message {{ display: flex; gap: 10px; margin-bottom: 12px; padding: 10px; border-radius: 10px; background: #fff0f5; }}
            .avatar {{ width: 40px; height: 40px; border-radius: 50%; }}
            .content {{ flex: 1; }}
            .author {{ font-weight: bold; color: #d48aa3; }}
            .time {{ font-size: 12px; color: #999; margin-left: 5px; }}
            .attachment {{ margin-top: 5px; }}
            .attachment img {{ max-width: 250px; border-radius: 8px; margin-top: 5px; }}
            .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #aaa; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <img src="YOUR_LOGO_URL_HERE" class="logo">
                <div class="title">🎟️ Cottage Tickets</div>
                <div>Ticket Transcript ✧</div>
            </div>
            <div class="info-card">
                <b>User:</b> {ticket_user.name if ticket_user else "Unknown"}<br>
                <b>Channel:</b> #{channel.name}<br>
                <b>Category:</b> {category_name if category_name else "Unknown"}<br>
                <b>Opened:</b> {opened_at}<br>
                <b>Handled by:</b> {claimed_by if claimed_by else "Unclaimed"}
            </div>
    """
    for msg in messages:
        time = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        author = html.escape(msg.author.name)
        content = html.escape(msg.content)
        avatar = msg.author.display_avatar.url
        attachments_html = ""
        for att in msg.attachments:
            if att.filename.lower().endswith(("png","jpg","jpeg","gif","webp")):
                attachments_html += f'<div class="attachment"><img src="{att.url}"></div>'
            else:
                attachments_html += f'<div class="attachment"><a href="{att.url}" target="_blank">📎 {att.filename}</a></div>'
        html_content += f"""
        <div class="message">
            <img src="{avatar}" class="avatar">
            <div class="content">
                <span class="author">{author}</span>
                <span class="time">{time}</span>
                <div>{content}</div>
                {attachments_html}
            </div>
        </div>
        """
    html_content += """
            <div class="footer">Cottage Tickets ✧ Transcript Generated</div>
        </div>
    </body>
    </html>
    """
    return html_content

async def send_transcript(channel, user):
    claimed_by = claimed_tickets.get(channel.id)
    html_content = await create_transcript(channel, claimed_by=claimed_by, ticket_user=get_ticket_owner(channel), category_name=channel.category.name if channel.category else "None")
    file = discord.File(io.BytesIO(html_content.encode()), filename="transcript.html")
    log_channel = bot.get_channel(CONFIG["log_channel"])
    embed = discord.Embed(title="🎟️ Ticket Closed", color=0xF8C8DC)
    embed.add_field(name="User", value=user.mention if user else "Unknown")
    embed.add_field(name="Channel", value=f"#{channel.name}")
    embed.add_field(name="Handled by", value=claimed_by if claimed_by else "Unclaimed")
    await log_channel.send(embed=embed, file=file)
    try:
        if user:
            await user.send("💖 Your ticket has been closed. Here is your transcript:", file=file)
    except: pass

# ---------------- PANELS ---------------- #
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
        view.add_item(discord.ui.Button(label="Support", emoji="<:CC_Ticket:1478922207110631446>", style=discord.ButtonStyle.secondary, custom_id="support"))
        view.add_item(discord.ui.Button(label="Partnership", emoji="<:CC_Ticket:1478922207110631446>", style=discord.ButtonStyle.secondary, custom_id="partnership"))
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

# ---------------- SUPPORT REASON SELECT ---------------- #
SUPPORT_REASON_MESSAGES = {
    "Hosting Giveaway": (
        "𑇙        ♡︎\n"
        "Host a Giveaway\n\n"
        "ᯇ    Type of Giveaway    ‼\n"
        "𖩩    Duration    ✿\n"
        "𑇓    Number of Winners    ☆\n"
        "ᯇ    Prize    ‼\n"
        "𖩩    Requirements    ✿"
    ),
    "Help / Question": (
        "𑇙        ♡︎\n"
        "Help / Question\n\n"
        "ᯇ    Question Topic    ‼\n"
        "𖩩    Details / Description    ✿\n"
        "𑇓    Screenshots / Evidence    ☆\n"
        "ᯇ    Urgency / Priority    ‼\n"
        "𖩩    Additional Notes    ✿"
    ),
    "Subscription Purchase": (
        "𑇙        ♡︎\n"
        "Subscription Purchase\n\n"
        "ᯇ    Subscription Type    ‼\n"
        "𖩩    Discord Username    ✿\n"
        "𑇓    Payment Method: Wrapping    ☆\n"
        "ᯇ    Do you understand you must uphold your order quota to keep your subscription?    ‼\n"
        "𖩩    Additional Notes    ✿"
    ),
    "Claim Perks": (
        "𑇙        ♡︎\n"
        "Claim Perks\n\n"
        "ᯇ    Perk Type    ‼\n"
        "𖩩    Discord Username    ✿\n"
        "𑇓    Subscription / Role claiming perks for    ☆\n"
        "𖩩    Additional Notes    ✿"
    ),
}


class SupportReasonSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Hosting Giveaway", description="Request to host a giveaway"),
            discord.SelectOption(label="Help / Question", description="General help or questions"),
            discord.SelectOption(label="Subscription Purchase", description="Purchase a subscription"),
            discord.SelectOption(label="Claim Perks", description="Claim your perks or rewards"),
        ]
        super().__init__(placeholder="Select your reason...", min_values=1, max_values=1, options=options, custom_id="support_reason")

    async def callback(self, interaction: discord.Interaction):
        reason = self.values[0]
        description = SUPPORT_REASON_MESSAGES.get(reason, "Please describe your issue ✧")
        embed = discord.Embed(description=description, color=0x1b1c23)
        await interaction.response.send_message(embed=embed)
        self.disabled = True
        await interaction.message.edit(view=self.view)


class SupportWelcomeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(SupportReasonSelect())
        self.add_item(discord.ui.Button(label="🔒 Close", custom_id="close", style=discord.ButtonStyle.secondary))


# ---------------- INTERACTIONS ---------------- #
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not interaction.data:
        return
    custom_id = interaction.data.get("custom_id")
    user = interaction.user
    guild = interaction.guild

    if not guild:
        return

    staff_role = guild.get_role(CONFIG["staff_permission_role"])

    if custom_id == "partnership":
        staff_overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        if staff_role:
            staff_overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        category = bot.get_channel(CONFIG["partnership_category"])
        name = generate_ticket_name(user, "partnership")
        channel = await guild.create_text_channel(name, category=category, overwrites=staff_overwrites)
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="🔒 Close", custom_id="close", style=discord.ButtonStyle.secondary))
        staff_mention = staff_role.mention if staff_role else ""
        await channel.send(staff_mention, embed=discord.Embed(title="🎟️ Ticket Created", description="Describe your inquiry ✧", color=0x1b1c23), view=view)
        await interaction.response.send_message(f"Created: {channel.mention}", ephemeral=True)

    elif custom_id == "support":
        staff_overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        if staff_role:
            staff_overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        category = bot.get_channel(CONFIG["support_category"])
        name = generate_ticket_name(user, "support")
        channel = await guild.create_text_channel(name, category=category, overwrites=staff_overwrites)
        staff_mention = staff_role.mention if staff_role else ""
        embed = discord.Embed(
            description=(
                "𑇙        ♡︎\n\n"
                "Please select your reason for opening below\n\n"
                "Our support team would be with you shortly"
            ),
            color=0x1b1c23
        )
        await channel.send(staff_mention, embed=embed, view=SupportWelcomeView())
        await interaction.response.send_message(f"Created: {channel.mention}", ephemeral=True)

    elif custom_id == "order":
        existing = count_user_order_tickets(guild, user)
        limit = max_order_tickets(user)
        if existing >= limit:
            await interaction.response.send_message(f"❌ You reached your limit ({existing}/{limit})", ephemeral=True)
            return
        category = bot.get_channel(CONFIG["order_unclaimed_category"])
        name = generate_ticket_name(user, "order_unclaimed")
        overwrites = {guild.default_role: discord.PermissionOverwrite(read_messages=False),
                      user: discord.PermissionOverwrite(read_messages=True, send_messages=True)}
        channel = await guild.create_text_channel(name, category=category, overwrites=overwrites)
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="🔒 Close", custom_id="close"))
        view.add_item(discord.ui.Button(label="📝 Claim", custom_id="claim"))
        await channel.send(f"{user.mention}", embed=discord.Embed(title="🛒 Order Ticket", description="Please wait for a chef ✧", color=0xF8C8DC), view=view)
        await interaction.response.send_message(f"Created: {channel.mention}", ephemeral=True)

    elif custom_id == "claim":
        channel = interaction.channel
        owner = get_ticket_owner(channel)
        claimed_tickets[channel.id] = interaction.user.name
        await channel.edit(name=generate_ticket_name(owner, "order_claimed"), category=bot.get_channel(CONFIG["order_claimed_category"]))
        await interaction.response.send_message("✅ Claimed!", ephemeral=True)

    elif custom_id == "close":
        channel = interaction.channel
        is_staff = staff_role in interaction.user.roles if staff_role else False
        owner = get_ticket_owner(channel)
        is_owner = owner and interaction.user.id == owner.id
        if not is_staff and not is_owner:
            await interaction.response.send_message("❌ Only staff or the ticket owner can close this ticket.", ephemeral=True)
            return
        await interaction.response.send_message("🔒 Closing ticket...", ephemeral=True)
        try:
            await send_transcript(channel, owner)
        except Exception as e:
            print(f"Transcript error: {e}")
        await channel.delete()

# ---------------- RENAME COMMAND ---------------- #
@bot.tree.command(name="rename", description="Rename the current ticket channel")
@discord.app_commands.describe(new_name="The new name for this ticket channel")
async def rename(interaction: discord.Interaction, new_name: str):
    staff_role = interaction.guild.get_role(CONFIG["staff_permission_role"])
    is_staff = staff_role in interaction.user.roles if staff_role else False
    if not is_staff and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Only staff can rename tickets.", ephemeral=True)
        return
    try:
        await interaction.channel.edit(name=new_name)
        embed = discord.Embed(description=f"✧ Channel renamed to **{new_name}**", color=0x1b1c23)
        await interaction.response.send_message(embed=embed)
    except discord.HTTPException as e:
        await interaction.response.send_message(f"❌ Failed to rename: {e}", ephemeral=True)


# ---------------- ACTIVITY TRACK ---------------- #
@bot.event
async def on_message(message):
    if message.author.bot: return
    name = message.channel.name.lower()
    if name.startswith(("support-","partnership-","unclaimed-","❗️unclaimed-","❕unclaimed-","order-")):
        last_message_time[message.channel.id] = datetime.datetime.utcnow()
    await bot.process_commands(message)

# ---------------- INACTIVITY AUTO-CLOSE ---------------- #
class StaffInactivityView(discord.ui.View):
    def __init__(self, channel_id):
        super().__init__(timeout=2*3600)
        self.channel_id = channel_id

    @discord.ui.button(label="✅ Close Ticket", style=discord.ButtonStyle.danger)
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = bot.get_channel(self.channel_id)
        owner = get_ticket_owner(channel)
        claimed_by = claimed_tickets.get(channel.id)
        html_content = await create_transcript(channel, claimed_by=claimed_by, ticket_user=owner, category_name=channel.category.name if channel.category else "None")
        file = discord.File(io.BytesIO(html_content.encode()), filename="transcript.html")
        log_channel = bot.get_channel(CONFIG["log_channel"])
        embed = discord.Embed(title="🎟️ Ticket Auto-Closed (Staff Approved)", color=0xF8C8DC)
        embed.add_field(name="User", value=owner.mention if owner else "Unknown")
        embed.add_field(name="Channel", value=f"#{channel.name}")
        embed.add_field(name="Handled by", value=claimed_by if claimed_by else "Unclaimed")
        await log_channel.send(embed=embed, file=file)
        try:
            if owner: await owner.send("💖 Your ticket was automatically closed (staff approved).", file=file)
        except: pass
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
                embed = discord.Embed(title="⚠️ Ticket Inactivity Notice", description=f"{staff_mention}\nThis ticket has been inactive for 24 hours. Do you want to close it?", color=0xF8C8DC)
                view = StaffInactivityView(channel_id)
                await channel.send(embed=embed, view=view)
            elif delta >= 93600:
                owner = get_ticket_owner(channel)
                claimed_by = claimed_tickets.get(channel.id)
                html_content = await create_transcript(channel, claimed_by=claimed_by, ticket_user=owner, category_name=channel.category.name if channel.category else "None")
                file = discord.File(io.BytesIO(html_content.encode()), filename="transcript.html")
                log_channel = bot.get_channel(CONFIG["log_channel"])
                embed = discord.Embed(title="🎟️ Ticket Auto-Closed (No Staff Response)", color=0xF8C8DC)
                embed.add_field(name="User", value=owner.mention if owner else "Unknown")
                embed.add_field(name="Channel", value=f"#{channel.name}")
                embed.add_field(name="Handled by", value=claimed_by if claimed_by else "Unclaimed")
                await log_channel.send(embed=embed, file=file)
                try:
                    if owner: await owner.send("💖 Your ticket was automatically closed due to inactivity (staff did not respond).", file=file)
                except: pass
                await channel.delete()
                last_message_time.pop(channel_id)
                staff_request_sent_channels.discard(channel_id)
        await asyncio.sleep(300)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.tree.sync()
    print("Slash commands synced")
    bot.loop.create_task(ticket_inactivity_loop())

# ---------------- RUN BOT ---------------- #
bot.run(os.getenv("TOKEN"))