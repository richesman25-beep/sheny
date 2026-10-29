# Obtenir un lien Internet public

Le dossier contient une application web prête pour un hébergement Python.
Les visiteurs utilisent leur navigateur sur ordinateur ou téléphone et n'installent pas Python.
L'application n'est pas publiée simplement en téléchargeant ce dossier.

## Option recommandée : Render

Prérequis : un compte GitHub et un compte Render pouvant lire votre dépôt.

1. Ouvrez le dépôt **richesman25-beep/sheny**, branche **trading-web**.
   Les fichiers applicatifs et `render.yaml` sont à la racine de cette branche.
   La branche `main` contient le projet d'origine.
2. Connectez votre compte GitHub à Render et autorisez l'accès à ce dépôt.
   Aucun dossier `.venv`, donnée personnelle ou clé API n'est nécessaire.
3. Dans Render, créez un **Blueprint**, sélectionnez le dépôt **sheny**,
   choisissez la branche **trading-web** et utilisez `render.yaml`.
   Render installe les dépendances et démarre le service. Vérifiez les conditions et tarifs
   affichés avant de valider la création ; le manifeste demande l'offre `free`.
4. Attendez que le déploiement soit opérationnel, puis ouvrez **l'adresse HTTPS fournie par Render**.
   C'est le lien que vous pourrez utiliser et partager. Aucune adresse publique n'est encore créée ici.

Si vous préférez créer un **Web Service** manuellement :

| Champ | Valeur |
| --- | --- |
| Runtime | Python |
| Branche | `trading-web` |
| Répertoire racine | racine du dépôt, là où se trouve `app.py` |
| Build command | `pip install --disable-pip-version-check -r requirements.txt` |
| Start command | `bash web-start.sh` |
| Variable `PYTHON_VERSION` | `3.12.14` |
| Health check | `/_stcore/health` |

Le port est lu dans `PORT`, fourni par l'hébergeur. Le serveur écoute sur `0.0.0.0`.
Render gère le certificat HTTPS et le proxy ; les protections CORS/XSRF de Streamlit restent actives.
Une offre gratuite peut mettre le service en veille ou limiter ses ressources ; le premier
chargement peut donc être lent. Le fichier local ne permet pas de vérifier les conditions
actuelles de votre compte.

## Alternative : Streamlit Community Cloud

Après avoir envoyé le code dans un dépôt GitHub, créez une application depuis votre
compte Streamlit Community Cloud. Sélectionnez le dépôt, sa branche et `app.py` comme
fichier principal. Choisissez Python 3.12 dans les réglages disponibles.
Les dépendances sont installées depuis `requirements.txt` et le service fournit son URL HTTPS.
`render.yaml` et `web-start.sh` ne sont pas nécessaires pour cette option.

## Vérifier après publication

- Le lien HTTPS ouvre « Atelier Trading » et affiche les graphiques de démonstration.
- L'onglet Simulation historique affiche le capital et le journal.
- Un CSV valide peut être importé, et un CSV invalide affiche un message explicite.
- Les téléchargements CSV et JSON fonctionnent.
- Testez aussi depuis votre téléphone et une seconde session de navigateur.

Ces contrôles ont été effectués sur le serveur de développement, sauf la publication
Internet et la vérification de l'hébergeur, qui nécessitent votre compte.

## Accès et données

Cette version n'a pas de comptes utilisateurs : toute personne disposant de l'URL peut
ouvrir l'outil. Elle ne contient aucun identifiant de courtier et n'envoie aucun ordre.
Les fichiers importés sont traités en mémoire sur le serveur d'hébergement, pas seulement
dans le navigateur. N'y importez pas de données confidentielles si vous ne souhaitez pas
les confier à l'hébergeur. Les imports ne sont pas sauvegardés durablement et un redémarrage
peut les effacer ; téléchargez vos rapports. Limite d'import : 20 Mo / 50 000 bougies.

## Tester sur un serveur existant

Installez les dépendances dans un environnement virtuel, activez-le, puis :

```bash
PORT=8501 bash web-start.sh
```

Pour un serveur public administré par vos soins, un reverse proxy HTTPS prenant en charge
les WebSockets doit être placé devant Streamlit. `web-start.sh` est destiné à l'hébergement ;
`start.sh` et `start.bat` restent les lanceurs pour une utilisation locale.
