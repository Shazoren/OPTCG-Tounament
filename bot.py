"""
One Piece TCG – Discord Tournament Bot
Run:  python bot.py
"""

import io
import os
from typing import Optional
import discord
from discord import app_commands
from dotenv import load_dotenv
import tournament as t_mod
from bracket_image import generate_bracket_image

load_dotenv()
TOKEN            = os.getenv("DISCORD_TOKEN", "")
GUILD_ID         = int(os.getenv("GUILD_ID", "0"))
ARBITRE_ROLE     = os.getenv("ARBITRE_ROLE_NAME", "Arbitre")

# ─── bot setup ───────────────────────────────────────────────────────────────

intents = discord.Intents.default()

class TournamentBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

bot = TournamentBot()

# ─── embeds ──────────────────────────────────────────────────────────────────

OP_RED = discord.Color.from_rgb(212, 60, 60)
OP_BLUE = discord.Color.from_rgb(60, 120, 212)
OP_GOLD = discord.Color.from_rgb(200, 160, 20)

def embed_ok(title: str, desc: str = "", color=OP_RED) -> discord.Embed:
    return discord.Embed(title=title, description=desc, color=color)

def embed_err(msg: str) -> discord.Embed:
    return discord.Embed(title="❌ Erreur", description=msg, color=discord.Color.dark_red())

# ─── permission check ────────────────────────────────────────────────────────

def is_arbitre(interaction: discord.Interaction) -> bool:
    if isinstance(interaction.user, discord.Member):
        return any(r.name == ARBITRE_ROLE for r in interaction.user.roles)
    return False

def arbitre_required(func):
    """Decorator: refuse if user doesn't have the Arbitre role."""
    import functools
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        if not is_arbitre(interaction):
            await interaction.response.send_message(
                embed=embed_err(f"Commande réservée aux **{ARBITRE_ROLE}**s."), ephemeral=True)
            return
        return await func(interaction, *args, **kwargs)
    return wrapper


# ════════════════════════════════════════════════════════════════════════════
#  § COMMANDE : /ouvrir_inscriptions  (Arbitre)
# ════════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="ouvrir_inscriptions", description="§ Ouvre les inscriptions au tournoi.")
@arbitre_required
async def cmd_open(interaction: discord.Interaction):
    result = t_mod.open_registration()
    if result == "error:already_open":
        await interaction.response.send_message(
            embed=embed_err("Un tournoi est déjà en cours d'inscription ou actif."), ephemeral=True)
        return
    embed = embed_ok(
        "🏴‍☠️ Inscriptions ouvertes !",
        "Utilisez `/inscription` pour vous inscrire au tournoi One Piece TCG.\n"
        "Un arbitre lancera le tournoi avec `/lancer_tournoi`."
    )
    await interaction.response.send_message(embed=embed)


# ════════════════════════════════════════════════════════════════════════════
#  COMMANDE : /inscription  (tous)
# ════════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="inscription", description="S'inscrire au tournoi en cours.")
async def cmd_register(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    name = interaction.user.display_name
    result = t_mod.register_player(uid, name)
    if result == "error:not_open":
        await interaction.response.send_message(
            embed=embed_err("Les inscriptions ne sont pas ouvertes."), ephemeral=True)
        return
    if result == "error:already_registered":
        await interaction.response.send_message(
            embed=embed_err("Tu es déjà inscrit(e) !"), ephemeral=True)
        return
    t = t_mod.get()
    embed = embed_ok(
        "✅ Inscription confirmée",
        f"**{name}** rejoint le tournoi !\n"
        f"Participants inscrits : **{len(t.participants)}**"
    )
    await interaction.response.send_message(embed=embed)


# ════════════════════════════════════════════════════════════════════════════
#  COMMANDE : /desinscrire  (tous)
# ════════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="desinscrire", description="Se désinscrire du tournoi avant son lancement.")
async def cmd_unregister(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    result = t_mod.unregister_player(uid)
    if result == "error:not_open":
        await interaction.response.send_message(
            embed=embed_err("Les inscriptions ne sont pas ouvertes."), ephemeral=True)
        return
    if result == "error:not_registered":
        await interaction.response.send_message(
            embed=embed_err("Tu n'es pas inscrit(e)."), ephemeral=True)
        return
    await interaction.response.send_message(
        embed=embed_ok("↩️ Désinscription", f"{interaction.user.display_name} s'est désinscrit(e)."))


# ════════════════════════════════════════════════════════════════════════════
#  COMMANDE : /participants  (tous)
# ════════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="participants", description="Liste des participants inscrits.")
async def cmd_participants(interaction: discord.Interaction):
    t = t_mod.get()
    if t.state == "idle":
        await interaction.response.send_message(
            embed=embed_err("Aucun tournoi en cours."), ephemeral=True)
        return
    if not t.participants:
        await interaction.response.send_message(
            embed=embed_ok("📋 Participants", "Aucun inscrit pour l'instant."))
        return
    lines = "\n".join(
        f"`{i+1}.` {t.player_names.get(uid, uid)}"
        for i, uid in enumerate(t.participants)
    )
    embed = embed_ok(f"📋 Participants ({len(t.participants)})", lines)
    await interaction.response.send_message(embed=embed)


# ════════════════════════════════════════════════════════════════════════════
#  § COMMANDE : /lancer_tournoi  (Arbitre)
# ════════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="lancer_tournoi", description="§ Lance le tournoi et génère le bracket.")
@arbitre_required
async def cmd_start(interaction: discord.Interaction):
    await interaction.response.defer()
    result = t_mod.start_tournament()
    if result == "error:wrong_state":
        await interaction.followup.send(
            embed=embed_err("Le tournoi n'est pas en phase d'inscription."), ephemeral=True)
        return
    if result == "error:not_enough_players":
        await interaction.followup.send(
            embed=embed_err("Il faut au minimum **2 participants** pour lancer le tournoi."), ephemeral=True)
        return

    t = t_mod.get()
    pending = t_mod.get_pending_matches(t)

    embed = embed_ok(
        "🏴‍☠️ Tournoi lancé !",
        f"**{len(t.participants)} joueurs** s'affrontent en double élimination.\n"
        f"**{len(pending)}** match(s) à jouer au premier tour."
    )

    # List first round matches
    if pending:
        lines = []
        for m in pending[:10]:
            p1 = t.player_names.get(m.player1, m.player1) if m.player1 else "BYE"
            p2 = t.player_names.get(m.player2, m.player2) if m.player2 else "BYE"
            lines.append(f"**M{m.match_id}** : {p1} vs {p2}  `[{m.bracket}]`")
        embed.add_field(name="Matchs du premier tour", value="\n".join(lines), inline=False)

    img_bytes = generate_bracket_image(t)
    file = discord.File(io.BytesIO(img_bytes), filename="bracket.png")
    embed.set_image(url="attachment://bracket.png")
    await interaction.followup.send(embed=embed, file=file)


# ════════════════════════════════════════════════════════════════════════════
#  COMMANDE : /bracket  (tous)
# ════════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="bracket", description="Affiche le bracket actuel sous forme d'image.")
async def cmd_bracket(interaction: discord.Interaction):
    await interaction.response.defer()
    t = t_mod.get()
    if t.state not in ("ongoing", "finished"):
        await interaction.followup.send(
            embed=embed_err("Aucun tournoi actif."), ephemeral=True)
        return
    img_bytes = generate_bracket_image(t)
    file = discord.File(io.BytesIO(img_bytes), filename="bracket.png")
    status = "🏆 Tournoi terminé" if t.state == "finished" else "🔴 En cours"
    embed = embed_ok(f"Bracket – {status}")
    embed.set_image(url="attachment://bracket.png")
    await interaction.followup.send(embed=embed, file=file)


# ════════════════════════════════════════════════════════════════════════════
#  § COMMANDE : /score  (Arbitre)
# ════════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="score", description="§ Rentrer le résultat d'un match.")
@app_commands.describe(
    match_id="ID du match (visible sur le bracket, ex: 3)",
    gagnant="@mention du joueur vainqueur (joueurs réels)",
    slot="Slot du gagnant : 1 ou 2 (alternative au @mention, fonctionne aussi pour les tests)"
)
@arbitre_required
async def cmd_score(interaction: discord.Interaction, match_id: int,
                    gagnant: Optional[discord.Member] = None, slot: Optional[int] = None):
    # Resolve winner_id from either @mention or slot number
    if gagnant is None and slot is None:
        await interaction.response.send_message(
            embed=embed_err("Précise le gagnant : **@mention** ou **slot** (1 ou 2)."), ephemeral=True)
        return

    t = t_mod.get()
    if t.state != "ongoing":
        await interaction.response.send_message(
            embed=embed_err("Aucun tournoi en cours."), ephemeral=True)
        return
    if match_id not in t.matches:
        await interaction.response.send_message(
            embed=embed_err(f"Match **M{match_id}** introuvable."), ephemeral=True)
        return

    m = t.matches[match_id]

    if gagnant is not None:
        winner_id = str(gagnant.id)
        winner_name = gagnant.display_name
    else:
        if slot not in (1, 2):
            await interaction.response.send_message(
                embed=embed_err("Le slot doit être **1** ou **2**."), ephemeral=True)
            return
        winner_id = m.player1 if slot == 1 else m.player2
        if winner_id is None:
            await interaction.response.send_message(
                embed=embed_err(f"Le slot {slot} du match **M{match_id}** est vide (BYE)."), ephemeral=True)
            return
        winner_name = t.player_names.get(winner_id, winner_id)

    result = t_mod.report_score(match_id, winner_id)

    if result == "error:already_played":
        await interaction.response.send_message(
            embed=embed_err(f"Le match **M{match_id}** a déjà été joué."), ephemeral=True)
        return
    if result == "error:invalid_winner":
        await interaction.response.send_message(
            embed=embed_err(f"**{winner_name}** ne participe pas au match **M{match_id}**."), ephemeral=True)
        return

    t = t_mod.get()
    m = t.matches[match_id]
    loser_id = m.player2 if winner_id == m.player1 else m.player1
    loser_name = t.player_names.get(loser_id, loser_id) if loser_id else "BYE"

    embed = embed_ok(
        f"✅ Résultat enregistré – M{match_id}",
        f"🏆 **Vainqueur :** {winner_name}\n"
        f"❌ **Éliminé(e) :** {loser_name}"
        + ("\n\n🎉 **Tournoi terminé !** Tapez `/leaderboard` pour voir le classement." if result == "finished" else "")
    )

    # Show next pending matches
    pending = t_mod.get_pending_matches(t)
    if pending and result != "finished":
        lines = []
        for pm in pending[:8]:
            p1 = t.player_names.get(pm.player1, pm.player1) if pm.player1 else "BYE"
            p2 = t.player_names.get(pm.player2, pm.player2) if pm.player2 else "BYE"
            lines.append(f"**M{pm.match_id}** : {p1} vs {p2}  `[{pm.bracket}]`")
        embed.add_field(name=f"Matchs en attente ({len(pending)})", value="\n".join(lines), inline=False)

    await interaction.response.send_message(embed=embed)

    # Post updated bracket image
    if t.matches:
        img_bytes = generate_bracket_image(t)
        file = discord.File(io.BytesIO(img_bytes), filename="bracket.png")
        bracket_embed = embed_ok("Bracket mis à jour")
        bracket_embed.set_image(url="attachment://bracket.png")
        await interaction.followup.send(embed=bracket_embed, file=file)


# ════════════════════════════════════════════════════════════════════════════
#  COMMANDE : /matchs_en_attente  (tous)
# ════════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="matchs_en_attente", description="Liste des matchs non encore joués.")
async def cmd_pending(interaction: discord.Interaction):
    t = t_mod.get()
    if t.state != "ongoing":
        await interaction.response.send_message(
            embed=embed_err("Aucun tournoi en cours."), ephemeral=True)
        return
    pending = t_mod.get_pending_matches(t)
    if not pending:
        await interaction.response.send_message(
            embed=embed_ok("Aucun match en attente", "Tous les matchs possibles ont été joués."))
        return
    lines = []
    for m in pending:
        p1 = t.player_names.get(m.player1, m.player1) if m.player1 else "BYE"
        p2 = t.player_names.get(m.player2, m.player2) if m.player2 else "BYE"
        lines.append(f"**M{m.match_id}** : {p1} vs {p2}  `[{m.bracket}]`")
    embed = embed_ok(f"⚔️ Matchs en attente ({len(pending)})", "\n".join(lines), color=OP_BLUE)
    await interaction.response.send_message(embed=embed)


# ════════════════════════════════════════════════════════════════════════════
#  COMMANDE : /leaderboard  (tous)
# ════════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="leaderboard", description="Classement des joueurs du tournoi.")
async def cmd_leaderboard(interaction: discord.Interaction):
    t = t_mod.get()
    if t.state == "idle":
        await interaction.response.send_message(
            embed=embed_err("Aucun tournoi en cours ou terminé."), ephemeral=True)
        return

    # Compute win counts from played matches
    win_counts: dict[str, int] = {}
    for m in t.matches.values():
        if m.winner and not m.winner.startswith("BYE"):
            win_counts[m.winner] = win_counts.get(m.winner, 0) + 1

    medals = ["🥇", "🥈", "🥉"]
    lines = []

    top10 = t.leaderboard[:10]
    if top10:
        for i, uid in enumerate(top10):
            name = t.player_names.get(uid, f"<@{uid}>")
            prefix = medals[i] if i < 3 else f"`#{i+1}`"
            wins = win_counts.get(uid, 0)
            lines.append(f"{prefix} **{name}** — {wins} victoire{'s' if wins > 1 else ''}")

    # Players still alive (not yet eliminated)
    still_in = [uid for uid in t.participants if uid not in t.leaderboard]
    if still_in:
        lines.append("")
        lines.append("*Encore en lice :*")
        for uid in still_in:
            name = t.player_names.get(uid, f"<@{uid}>")
            wins = win_counts.get(uid, 0)
            lines.append(f"⚔️ **{name}** — {wins} victoire{'s' if wins > 1 else ''}")

    title = "🏆 Classement final" if t.state == "finished" else "📊 Classement en cours"
    embed = embed_ok(title, "\n".join(lines) if lines else "Aucun joueur éliminé pour l'instant.", color=OP_GOLD)
    await interaction.response.send_message(embed=embed)


# ════════════════════════════════════════════════════════════════════════════
#  § COMMANDE : /test_remplir  (Arbitre) — TEST UNIQUEMENT
# ════════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="test_remplir", description="§ [TEST] Inscrit des faux joueurs pour tester le tournoi.")
@app_commands.describe(nombre="Nombre de faux joueurs à inscrire (2–16)")
@arbitre_required
async def cmd_test_fill(interaction: discord.Interaction, nombre: int = 4):
    if not (2 <= nombre <= 16):
        await interaction.response.send_message(
            embed=embed_err("Entre 2 et 16 joueurs."), ephemeral=True)
        return
    t = t_mod.get()
    if t.state != "registration":
        await interaction.response.send_message(
            embed=embed_err("Ouvre d'abord les inscriptions avec `/ouvrir_inscriptions`."), ephemeral=True)
        return

    noms = ["Luffy", "Zoro", "Nami", "Usopp", "Sanji",
            "Chopper", "Robin", "Franky", "Brook", "Jinbe",
            "Shanks", "Mihawk", "Hancock", "Ace", "Sabo", "Crocodile"]

    ajoutés = []
    for i in range(nombre):
        fake_id = f"TEST_{i+1:03d}"
        result = t_mod.register_player(fake_id, noms[i % len(noms)])
        if result == "ok":
            ajoutés.append(noms[i % len(noms)])

    embed = embed_ok(
        "🧪 Faux joueurs inscrits",
        f"**{len(ajoutés)} joueurs** ajoutés : {', '.join(ajoutés)}\n\n"
        "Lance le tournoi avec `/lancer_tournoi`, puis utilise `/score` pour simuler les matchs.",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed)


# ════════════════════════════════════════════════════════════════════════════
#  § COMMANDE : /annuler_tournoi  (Arbitre)
# ════════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="annuler_tournoi", description="§ Annule le tournoi en cours (inscription ou en jeu).")
@arbitre_required
async def cmd_cancel(interaction: discord.Interaction):
    t = t_mod.get()
    if t.state == "idle":
        await interaction.response.send_message(
            embed=embed_err("Aucun tournoi actif à annuler."), ephemeral=True)
        return

    previous_state = t.state
    participant_count = len(t.participants)

    # Wipe everything and return to idle
    t_mod.open_registration()
    data = t_mod._load()
    data.state = "idle"
    t_mod._save(data)

    state_label = {
        "registration": "en phase d'inscription",
        "ongoing": "en cours",
        "finished": "terminé",
    }.get(previous_state, previous_state)

    embed = discord.Embed(
        title="🚫 Tournoi annulé",
        description=(
            f"Le tournoi ({state_label}) avec **{participant_count} participant(s)** a été annulé.\n"
            "Toutes les données ont été effacées.\n\n"
            "Utilisez `/ouvrir_inscriptions` pour en démarrer un nouveau."
        ),
        color=discord.Color.dark_orange()
    )
    await interaction.response.send_message(embed=embed)


# ════════════════════════════════════════════════════════════════════════════
#  § COMMANDE : /reset_tournoi  (Arbitre)
# ════════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="reset_tournoi", description="§ Réinitialise complètement le tournoi.")
@arbitre_required
async def cmd_reset(interaction: discord.Interaction):
    t_mod.open_registration()   # resets everything and sets state to "registration"
    import tournament as _t
    data = _t._load()
    data.state = "idle"
    _t._save(data)
    await interaction.response.send_message(
        embed=embed_ok("🔄 Tournoi réinitialisé", "Toutes les données ont été effacées."))


# ─── events ──────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}  |  Serveur cible : {GUILD_ID}")


# ─── run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    bot.run(TOKEN)
