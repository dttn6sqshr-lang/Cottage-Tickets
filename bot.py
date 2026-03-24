# bot.py
import discord
from discord.ext import commands
from discord.utils import get
import os
import datetime
import html
import io

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

    "vip_order_roles": [1478947007979851908],
    "staff_order_roles": [
        1474547037344370952,
        1474546634968006827,
        1474546294990176471
    ],

    "log_channel": 1485800916199280801
}
# ---------------------------------------- #

ticket_counter = 0

# ---------- HELPERS ---------- #
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
        if user.name.lower() in channel.name.lower():
            if "unclaimed" in channel.name or "claimed" in channel.name:
                count += 1
    return count


async def create_transcript(channel):
    messages = []
    async for msg in channel.history(limit=None, oldest_first=True):
        messages.append(msg)

    html_content = "<html><body>"
    for msg in messages:
        time = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
        author = html.escape(msg.author.name)
        content = html.escape(msg.content)
        html_content += f"<p>[{time}] <b>{author}</b>: {content}</p>"
    html_content += "</body></html>"

    return html_content


async def send_transcript(channel, user, category):
    log_channel = bot.get_channel(CONFIG["log_channel"])

    html_content = await create_transcript(channel)
    file = discord.File(io.BytesIO(html_content.encode()), filename="transcript.html")

    embed = discord.Embed(
        title="🎟️ Ticket Closed",
        color=0xF8C8DC
    )
    embed.add_field(name="User", value=user.mention)
    embed.add_field(name="Category", value=category)
    embed.add_field(name="Closed", value=str(datetime.datetime.utcnow()))

    # Send to logs
    await log_channel.send(embed=embed, file=file)

    # DM user
    try:
        await user.send(
            content="💖 Your ticket has been closed. Here is your transcript:",
            file=file
        )
    except:
        pass


def get_ticket_owner(channel):
    for member in channel.members:
        if not member.bot:
            return member
    return None


# ---------- READY ---------- #
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


# ---------- PANEL COMMAND ---------- #
@bot.command()
@commands.has_permissions(administrator=True)
async def panel(ctx, type_: str):
    if type_ == "main":
        embed = discord.Embed(
            title="💖 Cottage Support Center",
            description="Choose an option below ✧",
            color=0xF8C8DC
        )

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="💖 Support", custom_id="support"))
        view.add_item(discord.ui.Button(label="🤝 Partnership", custom_id="partnership"))

        await ctx.send(embed=embed, view=view)

    elif type_ == "order":
        embed = discord.Embed(
            title="🛒 Order Tickets",
            description="Click below to open an order ticket ✧",
            color=0xF8C8DC
        )

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="🛒 Order", custom_id="order"))

        await ctx.send(embed=embed, view=view)


# ---------- INTERACTIONS ---------- #
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not interaction.data:
        return

    custom_id = interaction.data.get("custom_id")
    user = interaction.user
    guild = interaction.guild

    # SUPPORT / PARTNERSHIP
    if custom_id in ["support", "partnership"]:
        category_id = CONFIG["support_category"] if custom_id == "support" else CONFIG["partnership_category"]
        category = bot.get_channel(category_id)

        name = generate_ticket_name(user, custom_id)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        channel = await guild.create_text_channel(name, category=category, overwrites=overwrites)

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="🔒 Close", custom_id="close"))

        await channel.send(f"{user.mention}", embed=discord.Embed(
            title="🎟️ Ticket Created",
            description="Describe your issue ✧",
            color=0xF8C8DC
        ), view=view)

        await interaction.response.send_message(f"Created: {channel.mention}", ephemeral=True)

    # ORDER
    elif custom_id == "order":
        existing = count_user_order_tickets(guild, user)
        limit = max_order_tickets(user)

        if existing >= limit:
            await interaction.response.send_message(
                f"❌ You reached your limit ({existing}/{limit})",
                ephemeral=True
            )
            return

        category = bot.get_channel(CONFIG["order_unclaimed_category"])
        name = generate_ticket_name(user, "order_unclaimed")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        channel = await guild.create_text_channel(name, category=category, overwrites=overwrites)

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="🔒 Close", custom_id="close"))
        view.add_item(discord.ui.Button(label="📝 Claim", custom_id="claim"))

        await channel.send(f"{user.mention}", embed=discord.Embed(
            title="🛒 Order Ticket",
            description="Please wait for a chef ✧",
            color=0xF8C8DC
        ), view=view)

        await interaction.response.send_message(f"Created: {channel.mention}", ephemeral=True)

    # CLAIM
    elif custom_id == "claim":
        channel = interaction.channel
        owner = get_ticket_owner(channel)

        await channel.edit(
            name=generate_ticket_name(owner, "order_claimed"),
            category=bot.get_channel(CONFIG["order_claimed_category"])
        )

        await interaction.response.send_message("✅ Claimed!", ephemeral=True)

    # CLOSE
    elif custom_id == "close":
        channel = interaction.channel
        owner = get_ticket_owner(channel)

        await send_transcript(channel, owner, "ticket")

        await interaction.response.send_message("Closing...", ephemeral=True)
        await channel.delete()


# ---------- RUN ---------- #
bot.run(os.getenv("TOKEN"))