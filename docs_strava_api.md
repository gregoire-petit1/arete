# Intégration API Strava — Programme TMB 3j

Guide pour comprendre et reproduire l'intégration OAuth2 + API Strava dans ce projet Flask.

---

## 1. Créer une application Strava

1. Aller sur [strava.com/settings/api](https://www.strava.com/settings/api)
2. Remplir :
   - **Application Name** : nom libre
   - **Category** : Training
   - **Website** : URL de ton app (ou `http://localhost:5000`)
   - **Authorization Callback Domain** : domaine de ta callback (ex: `localhost`)
3. Récupérer le **Client ID** et le **Client Secret** affichés

---

## 2. Variables d'environnement requises

```bash
# Credentials Strava (globaux, ou par utilisateur — voir section 3)
STRAVA_CLIENT_ID=123456
STRAVA_CLIENT_SECRET=abc123...

# URI de callback — doit correspondre exactement à ce que Strava autorise
STRAVA_REDIRECT_URI=https://ton-domaine.fr/strava/callback
```

Support multi-utilisateur : chaque user peut avoir son propre compte Strava :

```bash
STRAVA_BASTIEN_CLIENT_ID=...
STRAVA_BASTIEN_CLIENT_SECRET=...
```

La fonction `get_strava_credentials(username)` dans `config.py` cherche d'abord
`STRAVA_<USERNAME>_CLIENT_ID/SECRET`, puis fallback sur les variables globales.

---

## 3. Flux OAuth2 (Authorization Code Flow)

```
Utilisateur → GET /strava/authorize
    → redirect vers https://www.strava.com/oauth/authorize
        ?client_id=...
        &redirect_uri=...
        &response_type=code
        &scope=activity:read_all
        &approval_prompt=auto
        &state=<token CSRF>
    → Strava redirige vers GET /strava/callback?code=...&state=...
    → échange du code contre access_token + refresh_token
    → sauvegarde dans strava_tokens.json
```

### Vérification CSRF

Un `state` aléatoire est généré à chaque autorisation et stocké en session :

```python
state = secrets.token_hex(16)
session["strava_oauth_state"] = state
```

La callback vérifie que le `state` retourné par Strava correspond avant de continuer.

### Échange du code

```python
resp = requests.post("https://www.strava.com/oauth/token", data={
    "client_id":     strava_cid,
    "client_secret": strava_secret,
    "code":          code,          # reçu dans ?code=
    "grant_type":    "authorization_code",
})
```

Réponse Strava :
```json
{
  "access_token":  "...",
  "refresh_token": "...",
  "expires_at":    1234567890,
  "athlete": {
    "id": 12345,
    "firstname": "Benjamin",
    "lastname":  "Lepourtois"
  }
}
```

Seuls `access_token`, `refresh_token`, `expires_at` et les infos athlete basiques sont conservés.

---

## 4. Stockage des tokens

Fichier JSON par utilisateur, droits `0o600` :

```
data/users/<username>/strava_tokens.json
```

```json
{
  "access_token":  "...",
  "refresh_token": "...",
  "expires_at":    1234567890,
  "athlete": {
    "id": 12345,
    "firstname": "Benjamin",
    "lastname":  "Lepourtois"
  }
}
```

Legacy (mode mono-utilisateur) : `data/strava_tokens.json`

---

## 5. Rafraîchissement automatique du token

`access_token` Strava expire après 6 heures. À chaque chargement de page, la
fonction `refresh_strava_token_if_needed()` est appelée :

```python
if time.time() > tokens["expires_at"] - 300:   # 5 min de marge
    resp = requests.post("https://www.strava.com/oauth/token", data={
        "client_id":     strava_cid,
        "client_secret": strava_secret,
        "grant_type":    "refresh_token",
        "refresh_token": tokens["refresh_token"],
    })
    # Mise à jour access_token, refresh_token, expires_at
    # + sauvegarde en fichier
```

Le `refresh_token` Strava est à usage unique : Strava en retourne un nouveau
à chaque refresh. Il faut impérativement mettre à jour le fichier après chaque refresh.

---

## 6. Récupération des activités

### Endpoint utilisé

```
GET https://www.strava.com/api/v3/athlete/activities
Authorization: Bearer <access_token>
```

### Paramètres

| Paramètre  | Type  | Description                              |
|------------|-------|------------------------------------------|
| `after`    | int   | Timestamp Unix — début de la période     |
| `before`   | int   | Timestamp Unix — fin de la période       |
| `per_page` | int   | Max 200, on utilise 50                   |
| `page`     | int   | Pagination, commence à 1                 |

### Pagination

L'API Strava ne retourne pas le nombre total d'activités. Le code boucle
jusqu'à recevoir une page incomplète (< 50 résultats) :

```python
while True:
    resp = requests.get(url, headers=..., params={..., "page": page})
    batch = resp.json()
    if not batch or len(batch) < 50:
        break
    page += 1
```

### Champs utilisés par activité

| Champ                  | Type    | Description                                  |
|------------------------|---------|----------------------------------------------|
| `id`                   | int     | Identifiant Strava                           |
| `name`                 | str     | Nom de l'activité                            |
| `type`                 | str     | `"Run"`, `"TrailRun"`, `"Hike"`, etc.        |
| `start_date`           | str     | ISO 8601, ex: `"2026-01-15T08:00:00Z"`       |
| `distance`             | float   | Mètres → divisé par 1000 pour avoir des km   |
| `total_elevation_gain` | float   | Mètres de dénivelé positif                   |
| `moving_time`          | int     | Secondes → divisé par 60 pour avoir des min  |
| `suffer_score`         | int     | Score d'effort Strava (non-dispo sans Summit)|
| `average_heartrate`    | float   | Utilisé pour calculer le TRIMP si pas de suffer_score |
| `max_heartrate`        | float   | Idem                                         |

---

## 7. Fallback suffer_score : formule TRIMP

Les utilisateurs non-premium Strava n'ont pas accès au `suffer_score` via l'API.
Le projet calcule un score équivalent via la formule Banister TRIMP :

```
TRIMP = durée_min × HRr × 0.64 × e^(1.92 × HRr) × 0.65
```

où `HRr = (FC_moy - FC_repos) / (FC_max_estimée - FC_repos)`

Constantes utilisées :
- `FC_repos = 55 bpm`
- `FC_max_estimée = max(FC_max × 1.05, 195)`
- Calibration `0.65` (ajustée sur 6 semaines de données réelles, jan–fév 2026)

Ce score est calculé uniquement si `suffer_score` est absent ou nul dans la réponse Strava.

---

## 8. Routes Flask

| Route                  | Méthode | Description                                       |
|------------------------|---------|---------------------------------------------------|
| `/strava/authorize`    | GET     | Redirige vers Strava pour autorisation OAuth2     |
| `/strava/callback`     | GET     | Reçoit le `code` Strava, échange contre les tokens |
| `/strava/disconnect`   | POST    | Supprime le fichier `strava_tokens.json`          |

---

## 9. Scope demandé

```
activity:read_all
```

Permet de lire **toutes** les activités (y compris celles marquées privées).
Si seules les activités publiques suffisent, utiliser `activity:read`.

---

## 10. Déconnexion

La déconnexion supprime simplement le fichier de tokens. Aucun appel API Strava
n'est fait pour révoquer le token — l'utilisateur peut le faire manuellement
depuis [strava.com/settings/apps](https://www.strava.com/settings/apps).

---

## 11. Checklist de déploiement

- [ ] App Strava créée sur strava.com/settings/api
- [ ] Domaine de callback enregistré dans l'app Strava
- [ ] Variables d'env `STRAVA_CLIENT_ID` et `STRAVA_CLIENT_SECRET` définies
- [ ] `STRAVA_REDIRECT_URI` correspond exactement à l'URL déclarée dans l'app Strava
- [ ] Répertoire `data/users/<username>/` accessible en écriture
- [ ] HTTPS en production (cookie de session `Secure`)
