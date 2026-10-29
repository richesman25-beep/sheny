# Atelier Trading — version utilisable

Application locale en français pour explorer des cours OHLCV, calculer des indicateurs,
dimensionner une position et simuler une stratégie sur un historique.
Elle n'envoie aucun ordre et ne nécessite ni compte de courtier ni clé API.

Pour une utilisation par un lien Internet, consultez **MISE_EN_LIGNE.md**.
La configuration Render et le lanceur `web-start.sh` sont fournis ; un compte
d'hébergement est nécessaire pour créer le lien HTTPS public.

## Lancer l'application

Prérequis : **Python 3.12 recommandé** (3.11 minimum), avec pip et venv.
Internet est nécessaire à la première installation des dépendances.

**Windows** : décompressez le dossier puis double-cliquez sur `start.bat`.
Si la commande `py` est absente, installez Python depuis python.org avec le lanceur Python.

**Linux / macOS** : dans le dossier décompressé, exécutez :

```bash
bash start.sh
```

Dans un navigateur **sur votre propre ordinateur**, ouvrez `http://127.0.0.1:8501`.
Gardez le terminal ouvert ; `Ctrl+C` arrête le serveur. L'application écoute uniquement
sur l'ordinateur local. Dans un environnement cloud, cette adresse ne donne pas de lien
public ; récupérez le dossier pour l'utiliser localement.

Installation manuelle / réparation d'une installation incomplète :

```bash
python -m venv .venv
# Linux / macOS
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
# Windows : remplacer .venv/bin/python par .venv\Scripts\python.exe
```

En cas de port occupé : arrêtez une ancienne instance, ou ajoutez
`--server.port 8502` à la commande manuelle.

## Premier usage

1. Commencez par **Démonstration** : les données sont fictives et reproductibles selon le scénario.
2. Explorez le graphique, les EMA et le RSI, puis la checklist dans **Scénario et risque**.
3. Indiquez le capital, le risque et les coûts adaptés à votre marché.
4. Consultez **Simulation historique** et téléchargez son journal CSV.
5. Pour vos propres cours, choisissez **Importer un CSV** et sélectionnez un export OHLCV.

Le nom de l'actif est une étiquette, pas un téléchargement de cours.
L'application ne contient pas de source de prix en direct. L'exemple fourni
`exemple_donnees_simulees.csv` est synthétique : ne le confondez pas avec un historique réel.

## Importer des données réelles

Exportez les bougies depuis votre fournisseur, puis utilisez ce format UTF-8 :

```csv
timestamp,open,high,low,close,volume
2026-01-01T00:00:00Z,100,102,99,101,1200
2026-01-01T01:00:00Z,101,103,100,102,1400
```

Les deux lignes illustrent seulement le format : **200 bougies minimum** pour l'analyse,
**202 minimum** pour la simulation ; un historique beaucoup plus long est préférable.
Les colonnes de prix doivent être numériques avec un point décimal. Les séparateurs
virgule, point-virgule et tabulation sont acceptés. `date`, `datetime` et `time` sont
acceptés comme noms alternatifs de la colonne de dates. Les noms de colonnes sont
insensibles à la casse. Les lignes sont triées ; les dates dupliquées, valeurs manquantes,
prix non positifs et bougies incohérentes sont refusés. Les timestamps Unix numériques
ne sont pas acceptés : convertissez-les en dates ISO 8601. Les dates sans fuseau sont
interprétées en UTC. Interface limitée à 20 Mo et 50 000 lignes.

Utilisez une fréquence régulière, une même unité de temps et uniquement des bougies
clôturées. Les trous de marché ne sont pas comblés automatiquement. La fermeture des
bougies et la qualité du fournisseur ne peuvent pas être vérifiées à partir du fichier seul.
Pour les actions, vérifiez le traitement des splits et dividendes chez le fournisseur.

Prix et capital doivent être dans la même devise. La taille est calculée en unités
de l'actif, sans prise en compte des pas de lot, contrats, multiplicateurs, devises
de compte différentes ou contraintes spécifiques du courtier.

## Corrections et règles

- **RSI de Wilder** : initialisation correcte avec 14 variations ; hausses seules = 100,
  baisses seules = 0, prix constant = 50. La période initiale reste indisponible.
- **ATR de Wilder** : moyenne initiale puis lissage récursif ; aucun remplissage à partir
  de données futures.
- **Signal** : prix et EMA 20/50/200 alignés, proximité de l'EMA 50 **et** RSI entre 40 et 60.
  Chaque critère affiché est réellement évalué. Aucun signal si la volatilité est nulle.
- **Supports/résistances** : extrêmes des 30 dernières bougies ; il ne s'agit pas de pivots confirmés.
- **Position** : budget de risque intégrant frais et glissement au stop, exposition plafonnée
  au capital, aucun levier. Le ratio gain/risque affiché est brut, avant coûts.

## Hypothèses de simulation

Les 200 premières bougies amorcent les indicateurs. Un signal n'est utilisé qu'après
la clôture de sa bougie ; l'entrée utilise l'ouverture suivante avec glissement adverse.
Stop et objectif sont recalculés depuis cette exécution et l'ATR connu au moment du signal.
Une position à la fois ; pas de réentrée sur la bougie de sortie.

Les frais sont déduits à l'entrée et à la sortie. Si stop et objectif sont tous deux
touchés pendant une bougie, le stop a priorité ; un gap défavorable au stop est exécuté
à l'ouverture, avec glissement. Une ouverture au-delà de l'objectif est comptée au prix
de l'objectif, sans amélioration favorable. Une position encore ouverte à la fin est
fermée au dernier cours, avec frais et glissement, et marquée `fin_echantillon` dans le journal.
La baisse maximale est calculée sur le capital valorisé aux clôtures, pas sur les variations intrabougie.

Les achats sont activés par défaut. La vente à découvert est facultative : modèle
théorique avec exposition plafonnée au capital, sans frais d'emprunt, marge de maintenance
ni liquidation. Elle n'établit pas la faisabilité d'une vente chez votre courtier.
Les pertes peuvent dépasser le risque prévu, voire le capital dans une simulation de vente
à découvert avec gap extrême. Aucune rentabilité n'est démontrée ; certains scénarios de
démonstration produisent des pertes. Aucun ajustement n'a été effectué pour afficher un gain.

Le spread, la liquidité, les exécutions partielles, le financement et la fiscalité ne sont
pas modélisés séparément. Les résultats concernent uniquement l'échantillon fourni,
sans validation hors échantillon. Utilisez d'abord ces outils pour apprendre et simuler.

## Exports et confidentialité

L'interface propose les données CSV, un rapport JSON et le journal du backtest CSV.
Les imports restent en mémoire dans le processus local ; aucun envoi de données de marché
à une API n'est programmé. Ils ne sont pas sauvegardés automatiquement. Téléchargez les
exports que vous souhaitez conserver. La télémétrie Streamlit est désactivée par les lanceurs.

## Utilisation en ligne de commande

```bash
.venv/bin/python trading_analysis_system.py
.venv/bin/python trading_analysis_system.py --backtest --output journal.csv
.venv/bin/python trading_analysis_system.py --csv mes_cours.csv --symbol ETH-USDT --capital 5000 --risk 1 --backtest --output journal.csv
```

La ligne de commande simule uniquement des achats. L'interface permet les réglages avancés.

## Vérifier l'installation

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Les tests couvrent notamment les valeurs RSI de référence, l'absence de fuite de données
futures, les frais et le glissement, les gaps, l'ordre des exécutions, les entrées invalides,
la cohérence comptable et l'interface Streamlit. Développé et vérifié sous Python 3.12/Linux ;
le lanceur Windows est fourni mais n'a pas été exécuté sous Windows.
