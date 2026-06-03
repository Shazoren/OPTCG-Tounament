# One Piece TCG – Bot Discord de tournoi

## Installation

```bash
pip install -r requirements.txt
```

Copier `.env.example` → `.env` et remplir :

```
DISCORD_TOKEN=   # Token du bot (Discord Developer Portal)
GUILD_ID=        # ID de ton serveur Discord (clic droit → Copier l'identifiant)
ARBITRE_ROLE_NAME=Arbitre   # Nom exact du rôle arbitre sur ton serveur
```

Lancer le bot :
```bash
python bot.py
```

---

## Commandes

| Commande | Rôle | Description |
|---|---|---|
| `/ouvrir_inscriptions` | § Arbitre | Ouvre les inscriptions, réinitialise le tournoi précédent |
| `/inscription` | Tous | S'inscrire au tournoi |
| `/desinscrire` | Tous | Se désinscrire (avant le lancement) |
| `/participants` | Tous | Voir la liste des inscrits |
| `/lancer_tournoi` | § Arbitre | Génère le bracket et lance le tournoi |
| `/bracket` | Tous | Affiche le bracket en image |
| `/score <match_id> <@gagnant>` | § Arbitre | Enregistre un résultat et met à jour le bracket |
| `/matchs_en_attente` | Tous | Liste les matchs à jouer |
| `/leaderboard` | Tous | Classement des joueurs |
| `/reset_tournoi` | § Arbitre | Réinitialise tout |

---

## Format : Double Élimination

- Perdre une fois → bracket **Losers**
- Perdre une seconde fois → **Éliminé**
- Le vainqueur du bracket Winners et le vainqueur du bracket Losers s'affrontent en **Grand Finals**

---

## Données

Les données sont sauvegardées dans `data/tournament.json` (créé automatiquement).
