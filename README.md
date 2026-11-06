# Veille technologique automatique

Système de veille qui lit chaque semaine des flux RSS et Atom choisis, filtre
les articles par thème et par mots-clés, et publie un résumé Markdown dans le
dépôt. Dependabot surveille en parallèle les dépendances du projet.

## Fonctionnement

1. `config.yaml` liste les thèmes (sécurité, réglementation, outils, IA),
   leurs mots-clés et leurs flux.
2. `veille.py` télécharge les flux, garde les articles des 7 derniers jours qui
   contiennent un mot-clé, et ignore ceux déjà vus (`seen.json`).
3. Le résumé est écrit dans `digests/AAAA-MM-JJ.md` et `digests/latest.md`.
   Les flux qui ne répondent pas sont listés en fin de résumé.
4. GitHub Actions lance le script chaque lundi matin et enregistre le résumé.
5. Dependabot propose chaque semaine une mise à jour des dépendances Python et
   des actions GitHub.

| Outil du cours | Rôle dans ce projet |
| --- | --- |
| Flux RSS / Atom | Sources : CERT-FR, CNIL, versions GitHub, arXiv, Hugging Face |
| Feedly | Lecture quotidienne des mêmes flux (importer la liste de `config.yaml`) |
| TLDR | Newsletter complémentaire, reçue par mail |
| Dependabot | Mises à jour automatiques des dépendances |

## Installation

```bash
pip install -r requirements.txt
python veille.py            # résumé des 7 derniers jours
python veille.py --days 30  # premier lancement : 30 jours
```

## Mise en ligne sur GitHub

1. Créer un dépôt et y envoyer ces fichiers.
2. Dans *Settings → Actions → General*, vérifier que les workflows ont
   l'autorisation *Read and write*.
3. Onglet *Actions* → *Veille hebdomadaire* → *Run workflow* pour un premier test.
4. Dans *Settings → Code security*, activer les alertes Dependabot.

## Personnaliser

- Ajouter un outil : copier une entrée de `outils` en changeant l'URL
  `https://github.com/<propriétaire>/<dépôt>/releases.atom`.
- Ajouter un mot-clé : l'ajouter à la liste `keywords` du thème.
- `all: true` garde tous les articles d'un flux, sans filtre.

Les URL marquées « à vérifier » dans `config.yaml` n'ont pas pu être testées
lors de la création : le premier résumé indique si l'une d'elles est en erreur.

## Esprit critique

Le système trouve l'information, il ne la valide pas. Chaque article se lit
avec la grille du cours : auteur et source, date, preuves, contexte.
