# Desk d'agents IA crypto

Un ensemble d'agents Claude Code spécialisés (veille, données de marché, mathématiques,
probabilités et risque, comptabilité, exécution Coinbase), branchés sur les MCP disponibles.

> ⚠️ Ces agents produisent des données et des mesures de risque, **pas des conseils financiers**.
> Les frameworks open source cités plus bas montrent tous un écart important entre résultats
> simulés et réels. Commencez avec un petit portefeuille Coinbase dédié, que vous pouvez perdre.

---

## 1. Inventaire des MCP disponibles dans cette session

| MCP | État | Rôle pour le desk |
|---|---|---|
| **CoinGecko** | ✅ connecté, testé | Prix, historique, dominance, secteurs, tendances, **news crypto**. Source principale. |
| WebSearch / WebFetch (intégrés) | ✅ | Veille macro, régulation, vérification des sources primaires. |
| **claude-code-remote** | ✅ | Crée des sessions agents dans le cloud et des **tâches planifiées** (ex. briefing tous les matins). |
| **Notion** | ✅ | `notion-spawn-session` / `notion-search-agents` : lancer des agents Notion ; archiver les briefings. |
| **Vercel** | ✅ | Sandboxes, `list_agent_runs` : héberger un agent qui tourne en continu. |
| **Supabase** | ✅ | Base de données pour l'historique des prix, des signaux et du journal de trades ; edge functions. |
| Gmail / Google Calendar | ✅ | Envoyer les alertes, caler les dates macro (Fed, CPI). |
| Google Drive | ✅ | Stocker exports CSV Coinbase et rapports. |
| QuickBooks (plugin small-business) | ✅ | Comptabilité si l'activité passe par une entreprise. |
| Zapier (plugin) | ✅ | Relier les alertes à d'autres apps. |
| browser-use, desktop-commander | ✅ | Automatisation navigateur / poste local. |
| LSEG, Daloopa, Exa, Nimble, Airtable… | 🔒 authentification requise | Données financières pro (taux, actions, macro). À autoriser dans les réglages des connecteurs claude.ai. |
| bigdata.com, Xero, HubSpot… | ❌ échec de connexion | Le serveur a refusé la connexion (enregistrement OAuth non supporté). |
| **Coinbase** | ➕ ajouté dans `.mcp.json` | À authentifier (voir § 4). |

Aucun MCP de cette liste n'est « un agent » à lui seul : ce sont des **outils**. Les agents sont
définis ici, dans `.claude/agents/`, et chacun ne reçoit que les outils dont il a besoin.

---

## 2. Ce qui existe sur GitHub (recherche de novembre 2026)

| Projet | Domaine | À retenir |
|---|---|---|
| [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | Trading multi-agents | Le plus suivi. Simule une société de trading : analystes (fondamental, sentiment, news, technique) → débat chercheurs haussiers/baissiers → trader → équipe risque. **Repris ici** : séparation des rôles + avocat du diable + veto du risque. |
| [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | Hedge fund éducatif | Agents « à la manière de » grands investisseurs ; fork crypto : `51bitquant/ai-hedge-fund-crypto`. Démonstration, pas de trading réel. |
| [AI4Finance-Foundation/FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) | Analyse financière | Plateforme d'agents pour l'analyse (rapports, valorisation), pas un robot de trading. |
| [LLMQuant/awesome-trading-agents](https://github.com/LLMQuant/awesome-trading-agents) | Liste | Catalogue des projets d'agents de trading. |
| EthanAlgoX/LLM-TradeBot, olaxbt/ai-market-maker | Crypto | Multi-agents crypto avec exécution (Binance) / market making. À n'utiliser qu'en lecture de code. |
| [vas3k/TaxHacker](https://github.com/vas3k/TaxHacker) | Comptabilité | Extraction IA de reçus/relevés, conversion historique incluant la crypto. |
| Bitwave CLI / Bitwave Agentic | Comptabilité crypto | Grand livre texte pilotable par un agent, support natif des actifs numériques. |
| accountant24, Open Accountant | Compta perso | Agents de comptabilité locaux (hledger) ; sync Coinbase en version payante pour Open Accountant. |
| [coinbase/agentkit](https://github.com/coinbase/agentkit) | Wallet onchain | SDK pour agents avec wallet (Base, x402). Différent de l'API de trading. |

---

## 3. Les agents créés

| Agent (`.claude/agents/`) | Spécialité | Outils | Peut trader ? |
|---|---|---|---|
| `crypto-news-sentinel` | Veille news, régulation, hacks, macro | CoinGecko news/trending, WebSearch, WebFetch | Non |
| `market-data-analyst` | Prix, volumes, dominance, secteurs, séries | CoinGecko (marché) | Non |
| `quant-mathematician` | Rendements, volatilité, Sharpe/Sortino, drawdown, corrélations | CoinGecko + `quant.py` | Non |
| `risk-probabilist` | VaR/CVaR, Monte Carlo, Kelly, taille de position, veto | CoinGecko + `quant.py` + `risk_limits.json` | Non |
| `crypto-accountant` | Journal, prix de revient, PnL, fiscalité (2086, 3916-bis…) | CoinGecko, WebSearch, Python | Non |
| `coinbase-executor` | Soldes, aperçu et passage d'ordre | Coinbase MCP / CLI | **Oui, après confirmation** |

Commandes d'orchestration (`.claude/commands/`) :
- `/crypto-briefing BTC ETH SOL` : news + marché en parallèle, puis quant + risque, puis synthèse.
- `/trade-proposal acheter 50 USDC de BTC-USDC, stop 62000, objectif 80000` : dossier complet avec
  verdict du risque ; **n'exécute rien** sans votre confirmation explicite.

### Boîte à outils quantitative (`ai_agents/quant/quant.py`)
Python standard, sans dépendance. Les agents l'appellent pour que **chaque chiffre soit calculé**.
```bash
python3 ai_agents/quant/quant.py stats      < ai_agents/data/bitcoin_90d.json
python3 ai_agents/quant/quant.py var --confidence 0.99 --horizon 7 < ai_agents/data/bitcoin_90d.json
python3 ai_agents/quant/quant.py montecarlo --days 30 --target 80000 --stop 60000 --zero-drift < ai_agents/data/bitcoin_90d.json
python3 ai_agents/quant/quant.py size --capital 1000 --risk-pct 1 --entry 68800 --stop 65000
python3 ai_agents/quant/quant.py kelly --win-prob 0.55 --win-loss-ratio 1.5
cd ai_agents/quant && python3 -m unittest -v test_quant
```
Le script accepte directement la réponse JSON de CoinGecko `get-coin-market-chart` et en déduit le
pas de temps (CoinGecko renvoie ~120 points, soit un point toutes les ~18 h sur 90 jours).

Exemple réel (BTC, 90 jours au 13/11/2026, prix 68 800 $) : volatilité annualisée ≈ 41 %,
drawdown max ≈ −20 %, excess kurtosis ≈ 3,2 (queues épaisses), VaR 95 % 1 jour ≈ 3,3 %.
Monte Carlo 30 jours sans dérive : P(toucher 80 000 avant 60 000) ≈ 17 %, P(l'inverse) ≈ 20 %.

### Garde-fous
- `ai_agents/config/risk_limits.json` : 50 $ max par ordre, 150 $/jour, stop obligatoire, pas de
  dérivés ni de retraits, liste blanche de paires. **Modifiez ces valeurs vous-même.**
- `.claude/settings.json` : chaque appel au MCP `coinbase` et chaque `coinbase orders create/cancel`,
  `convert`, `transfer` demande votre approbation manuelle ; `withdraw`/`send` sont interdits.
- Seul `coinbase-executor` peut voir les outils Coinbase ; les autres agents ont une liste d'outils fermée.
- `ai_agents/ledger/` et `ai_agents/data/` sont exclus de git (données privées).

---

## 4. Connecter Coinbase — procédure

Coinbase propose officiellement **« Coinbase for Agents »**, qui donne accès à Coinbase Advanced
Trade (900+ paires spot, plus futures US et actions US selon l'éligibilité). Deux voies :

### Étape 0 — Préparer un portefeuille isolé (fortement recommandé)
1. Sur **coinbase.com** (pas l'app mobile), créez un portefeuille séparé, par ex. « Agent ».
2. Transférez-y uniquement la somme que vous acceptez de perdre.
3. Vérifiez que votre compte a accès à Advanced Trade dans votre pays.
4. Il n'existe **pas de mode paper trading** documenté : tout ordre est réel.

### Voie A — MCP distant (OAuth, sans clé API) — configurée dans `.mcp.json`
1. Sur votre ordinateur, dans ce dépôt, lancez Claude Code (le fichier `.mcp.json` déclare le serveur ;
   l'équivalent manuel est `claude mcp add coinbase --transport http https://agents.coinbase.com/mcp`).
2. Tapez `/mcp`, choisissez **coinbase → Authenticate**.
3. Connectez-vous à Coinbase et, sur l'écran d'autorisation, **ne cochez que le portefeuille « Agent »**.
4. Testez en lecture : « Utilise coinbase-executor pour afficher mes soldes. »
5. Pour révoquer : <https://accounts.coinbase.com/security/connections>.

### Voie B — CLI locale avec clé API CDP (la plus fiable pour exécuter des ordres)
1. Installez Node.js 22+, puis :
   ```bash
   npm install -g @coinbase/coinbase-cli
   coinbase --version
   # Linux uniquement (trousseau de clés) :
   which secret-tool || sudo apt install -y libsecret-tools
   ```
2. Créez une clé sur <https://portal.cdp.coinbase.com/api-keys/secret> :
   Advanced Settings → **Coinbase App & Advanced Trade** → portefeuille « Agent » →
   permissions **Trade** + **Transfer** (Transfer = entre vos propres portefeuilles, pas de retrait
   externe). Téléchargez le JSON : le secret n'est affiché qu'une fois.
3. Rangez la clé **hors du dépôt** (ex. `~/.config/coinbase/agent_key.json`, `chmod 600`) puis :
   ```bash
   coinbase env live --key-file ~/.config/coinbase/agent_key.json
   coinbase env        # doit afficher "live" et l'ID de la clé
   coinbase balance    # doit renvoyer vos soldes en JSON
   ```
4. Essayez d'abord à blanc :
   ```bash
   coinbase orders preview product_id=BTC-USDC side=BUY type=market quote_size=10
   coinbase orders create  product_id=BTC-USDC side=BUY type=market quote_size=10 --dry-run
   ```
5. Ne collez **jamais** la clé dans le chat, un fichier suivi par git ou un environnement cloud partagé.

### Pourquoi pas dans cette session cloud ?
Cette session tourne dans un conteneur éphémère dans le cloud : l'authentification OAuth du MCP
et la clé API doivent rester **sur votre machine**. Clonez la branche, ouvrez Claude Code en local
et suivez la voie A ou B ; les agents et garde-fous du dépôt seront chargés automatiquement.

### Premier usage conseillé
1. `/crypto-briefing BTC ETH` (aucun accès Coinbase nécessaire).
2. « coinbase-executor : affiche mes soldes du portefeuille Agent. »
3. `/trade-proposal acheter 10 USDC de BTC-USDC à cours limité, stop -8 %` → lire le verdict.
4. Seulement ensuite, confirmer explicitement un premier petit ordre.

### Sources
- Coinbase MCP : <https://docs.cdp.coinbase.com/ai-agents/coinbase-for-agents/coinbase-mcp>
- Comparatif des outils agents Coinbase : <https://docs.cdp.coinbase.com/get-started/build-with-ai/comparing-agentic-tools>
- AgentKit et MCP : <https://docs.cdp.coinbase.com/agent-kit/core-concepts/model-context-protocol>
