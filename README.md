# memo

Cartes mémo (type Quizlet) pour réviser « Culture économique & financière 2 ». Flask + SQLite + Vue (CDN) + KaTeX.
Accès Tailscale uniquement, sans authentification.

## Règles
Constantes dans `config.toml` : 2 bonnes réponses consécutives (une erreur remet le compteur à zéro) valident une carte pour la session, 2 sessions la rendent acquise,
15 cartes max par session : 70 % nouvelles, 15 % acquises, 5 % validées, 10 % en apprentissage (ratios de `config.toml`, une catégorie courte est complétée par les autres ; une carte validée réussie du premier coup n'exige qu'une bonne réponse), une carte ratée revient 3 rangs plus loin.
Les statuts sont calculés à la volée depuis la table `answers` (journal en ajout seul).
Une erreur sur une carte acquise la repasse « en apprentissage ».

## Développement
```
python -m venv venv && venv/bin/pip install flask pytest
venv/bin/python -m pytest tests          # tests du moteur
venv/bin/python import_cards.py cards/cefi2.json --db data/memo.db
MEMO_DB=data/memo.db venv/bin/python app.py    # http://127.0.0.1:5005
```
Variables : `MEMO_HOST` (défaut 127.0.0.1), `MEMO_PORT` (défaut 5005), `MEMO_DB`.

## Déploiement
Depuis l'hôte : `deploy/deploy.sh` (LXC `web`, `/root/memo`, `memo.service`, `http://100.67.37.21:5005`).
Port 5005 : 5004 est pris par Synapse. L'import des cartes se lance sur le LXC.
