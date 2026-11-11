# Lézarde : mise en ligne sans serveur (gratuit)

L'appli tient en un site statique : `index.html` plus `data/secheresse.json`.
Chaque jour, GitHub télécharge la base officielle Géorisques (GASPAR), regénère `data/secheresse.json` et remet le site à jour. Il n'y a ni serveur ni abonnement.

## Mise en place (environ 10 minutes, une seule fois)

1. Crée un compte gratuit sur github.com.
2. Crée un dépôt public nommé `lezarde`, puis ajoute-y tous les fichiers de ce dossier, dossier caché `.github` compris.
3. Dans le dépôt, va dans **Settings → Pages → Source : Deploy from a branch → main / (root)**. Le site sera en ligne à l'adresse `https://<ton-pseudo>.github.io/lezarde/`.
4. Va dans **Actions → Mise à jour Géorisques → Run workflow** pour lancer la première mise à jour. Le fichier de démonstration est alors remplacé par la France entière.
5. Ensuite, tout se fait seul, tous les matins.

## Fichiers

- `index.html` : l'appli (recherche par commune, compte à rebours, liste d'actions, courriers).
- `data/secheresse.json` : les arrêtés sécheresse par commune (code INSEE → nom et liste des arrêtés : début, fin, date de parution au JO).
- `scripts/build_data.py` : télécharge `https://files.georisques.fr/GASPAR/gaspar.zip` et produit le JSON. Si la source paraît cassée, le fichier existant est conservé.
- `.github/workflows/maj-georisques.yml` : lance le script chaque jour.

## Prochaines étapes

- **Alertes e-mail** : la même tâche GitHub peut envoyer les e-mails via Brevo (300 e-mails par jour gratuits). Les inscriptions passent par un formulaire Brevo intégré à la page. Toujours sans serveur.
- **Nom de domaine** : par exemple lezarde.fr, à brancher sur GitHub Pages (environ 10 € par an).
- **Fraîcheur des données** : Géorisques est parfois mis à jour avec retard par rapport au Journal officiel. Une deuxième source pourra être ajoutée plus tard : l'API Légifrance, gratuite avec une clé.
