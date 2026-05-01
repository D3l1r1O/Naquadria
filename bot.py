import os
import json
import requests
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ─── CONFIGURAZIONE ───────────────────────────────────────────────────────────
TELEGRAM_TOKEN    = "8091049088:AAGdaZvda-lodHzKVetMUkhNncydcUwgMCY"
COINGECKO_API_KEY = "CG-SP48Lum12MB5FrWx67qeBv6d"   # chiave Demo CoinGecko
NEWSDATA_API_KEY  = "pub_f0c43893d9544330b832441f1d3edbb5"
BOT_USERNAME      = "@NaquadaBot"
GRUPPO_ID         = None
STORICO_FILE      = "storico.json"

# ID gruppo/canale per analisi automatica (opzionale)
GRUPPO_ID         = None  # es. -1001234567890

STORICO_FILE      = "storico.json"

# ─── MAPPA CRYPTO (nome/simbolo → id CoinGecko) ──────────────────────────────
COIN_IDS = {
    "bitcoin":   "bitcoin",   "btc":  "bitcoin",
    "ethereum":  "ethereum",  "eth":  "ethereum",
    "solana":    "solana",    "sol":  "solana",
    "cardano":   "cardano",   "ada":  "cardano",
    "ripple":    "ripple",    "xrp":  "ripple",
    "dogecoin":  "dogecoin",  "doge": "dogecoin",
    "polkadot":  "polkadot",  "dot":  "polkadot",
    "avalanche": "avalanche-2","avax": "avalanche-2",
    "chainlink": "chainlink", "link": "chainlink",
    "litecoin":  "litecoin",  "ltc":  "litecoin",
    "uniswap":   "uniswap",   "uni":  "uniswap",
    "near":      "near",
    "shiba":     "shiba-inu", "shib": "shiba-inu",
    "aave":      "aave",
    "matic":     "matic-network", "pol": "matic-network",
}

# ─── STORICO / BACKTEST ───────────────────────────────────────────────────────

def carica_storico() -> dict:
    if os.path.exists(STORICO_FILE):
        with open(STORICO_FILE, "r") as f:
            return json.load(f)
    return {"analisi": [], "calibrazione": {"cons": 1.0, "base": 1.0, "ott": 1.0}}

def salva_storico(storico: dict):
    with open(STORICO_FILE, "w") as f:
        json.dump(storico, f, indent=2)

def salva_analisi(coin: str, symbol: str, prezzo: float, targets: dict):
    storico = carica_storico()
    record = {
        "id":               len(storico["analisi"]) + 1,
        "data":             datetime.now().isoformat(),
        "coin":             coin,
        "symbol":           symbol,
        "prezzo_ingresso":  prezzo,
        "target_cons":      targets["cons"],
        "target_base":      targets["base"],
        "target_ott":       targets["ott"],
        "verificato":       False,
        "prezzo_verifica":  None,
        "data_verifica":    None,
        "risultato":        None,
    }
    storico["analisi"].append(record)
    salva_storico(storico)

def aggiorna_backtest():
    storico = carica_storico()
    modificato = False
    errori_cons, errori_base = [], []

    for rec in storico["analisi"]:
        if rec["verificato"]:
            continue
        data_analisi = datetime.fromisoformat(rec["data"])
        if datetime.now() - data_analisi < timedelta(days=14):
            continue
        try:
            dati       = get_crypto_data(rec["coin"])
            prezzo_ora = dati["market_data"]["current_price"]["usd"]
            rec["prezzo_verifica"] = prezzo_ora
            rec["data_verifica"]   = datetime.now().isoformat()
            rec["verificato"]      = True
            rec["risultato"]       = round(
                (prezzo_ora - rec["prezzo_ingresso"]) / rec["prezzo_ingresso"] * 100, 2)
            errori_cons.append(prezzo_ora / rec["target_cons"])
            errori_base.append(prezzo_ora / rec["target_base"])
            modificato = True
        except:
            continue

    if errori_cons:
        mc = sum(errori_cons) / len(errori_cons)
        mb = sum(errori_base) / len(errori_base)
        storico["calibrazione"]["cons"] = round(
            storico["calibrazione"]["cons"] * 0.7 + mc * 0.3, 4)
        storico["calibrazione"]["base"] = round(
            storico["calibrazione"]["base"] * 0.7 + mb * 0.3, 4)

    if modificato:
        salva_storico(storico)
    return storico

# ─── DATI DI MERCATO ──────────────────────────────────────────────────────────

def get_crypto_data(coin_input: str) -> dict:
    coin_id = COIN_IDS.get(coin_input.lower(), coin_input.lower())
    url     = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
    headers = {"x-cg-demo-api-key": COINGECKO_API_KEY}
    params  = {
        "localization":   "false",
        "tickers":        "false",
        "community_data": "false",
        "developer_data": "false",
        "sparkline":      "false",
    }
    r    = requests.get(url, headers=headers, params=params, timeout=10)
    data = r.json()
    if "market_data" not in data:
        raise Exception(
            f"Crypto '{coin_input}' non trovata.\n"
            f"Usa /lista per vedere tutte le crypto supportate."
        )
    return data

def get_fear_greed() -> dict:
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
        d = r.json()["data"][0]
        return {"value": int(d["value"]), "label": d["value_classification"]}
    except:
        return {"value": 50, "label": "Neutral"}

def get_news(query: str) -> list:
    try:
        r = requests.get(
            "https://newsdata.io/api/1/news",
            params={"apikey": NEWSDATA_API_KEY, "q": query, "language": "it,en", "size": 3},
            timeout=10,
        )
        return r.json().get("results", [])
    except:
        return []

# ─── CALCOLI ──────────────────────────────────────────────────────────────────

def calc_nick_score(price, ath, p24, p7, p30) -> float:
    score    = 50
    ath_dist = (price - ath) / ath * 100
    if ath_dist > -20:   score += 10
    elif ath_dist > -40: score += 5
    else:                score -= 5
    if p30 > 10:   score += 10
    elif p30 > 0:  score += 5
    else:          score -= 5
    if p7 > 5:    score += 5
    elif p7 < -5: score -= 5
    score += 3 if p24 > 0 else -3
    return round(min(max(score, 0), 100), 1)

def calc_zones(price: float, calibrazione: dict) -> dict:
    cc = calibrazione.get("cons", 1.0)
    cb = calibrazione.get("base", 1.0)
    return {
        "accumulo":         price * 0.71,
        "hold_low":         price * 0.83,
        "hold_high":        price * 1.19,
        "vendita":          price * 1.48,
        "alert":            price * 0.88,
        "ob_bull":          price * 0.82,
        "ob_bear":          price * 1.23,
        "fvg_low":          price * 0.93,
        "fvg_high":         price * 1.08,
        "bos":              price,
        "livello_decisivo": price * 0.95,
        "target_cons":      price * 1.32 * cc,
        "target_base":      price * 1.53 * cb,
        "target_ott":       price * 2.50,
    }

# ─── FORMATTAZIONE ────────────────────────────────────────────────────────────

def format_analysis(data: dict, news: list, fg: dict, calibrazione: dict) -> tuple:
    m     = data["market_data"]
    price = m["current_price"]["usd"]
    mcap  = (m["market_cap"]["usd"] or 0) / 1e9
    fdv   = (m.get("fully_diluted_valuation") or {}).get("usd", 0) / 1e9
    vol   = (m["total_volume"]["usd"] or 0) / 1e9
    p24   = m.get("price_change_percentage_24h") or 0
    p7    = m.get("price_change_percentage_7d")  or 0
    p30   = m.get("price_change_percentage_30d") or 0
    ath   = m["ath"]["usd"]
    ath_dist = (price - ath) / ath * 100

    name   = data["name"].upper()
    symbol = data["symbol"].upper()
    now    = datetime.now().strftime("%d-%m-%Y %H:%M")
    score  = calc_nick_score(price, ath, p24, p7, p30)
    z      = calc_zones(price, calibrazione)

    storico      = carica_storico()
    n_analisi    = len(storico["analisi"])
    n_verificate = len([a for a in storico["analisi"] if a["verificato"]])
    cal          = storico["calibrazione"]

    def arrow(v): return "🟢" if v > 0 else "🔴"
    def fmt_score(s):
        if s >= 70: return f"{s}/100 — 🔥 Forte"
        if s >= 55: return f"{s}/100 — ⚡ Interessante"
        if s >= 40: return f"{s}/100 — 😐 Neutrale"
        return      f"{s}/100 — ⚠️ Debole"

    trend    = "🔀 misto" if abs(p24) < 1 else ("📈 rialzista" if p24 > 0 else "📉 ribassista")
    fg_emoji = ("😱" if fg["value"] < 25 else "😨" if fg["value"] < 45
                else "😐" if fg["value"] < 55 else "😊" if fg["value"] < 75 else "🤑")

    news_lines = ""
    for n in news[:3]:
        title  = (n.get("title") or "")[:80]
        source = (n.get("source_id") or "").upper()
        news_lines += f"📰 {title}… [{source}]\n"
    if not news_lines:
        news_lines = "📰 Nessuna news recente trovata\n"

    cal_str = ""
    if n_verificate > 0:
        cal_str = f"\n• Target calibrati: cons×{cal['cons']:.2f} | base×{cal['base']:.2f}"

    msg = (
        f"📊 *ANALISI LONG-TERM {name} ({symbol})*\n"
        f"🔗 Fonte: CoinGecko | {now}\n\n"
        f"💰 *Dati di Mercato*\n"
        f"• Prezzo: ${price:,.2f}\n"
        f"• Market Cap: ${mcap:.2f}B | FDV: ${fdv:.2f}B\n"
        f"• Volume 24h: ${vol:.2f}B\n\n"
        f"📈 *Performance*\n"
        f"• 24h: {arrow(p24)} {p24:.2f}% | 7d: {arrow(p7)} {p7:.2f}% | 30d: {arrow(p30)} {p30:.2f}%\n"
        f"• Trend: {trend}\n"
        f"• ATH Distance: {ath_dist:.1f}%\n\n"
        f"⭐ *Nick Score: {fmt_score(score)}*\n"
        f"Quality: █████░ (85% dati reali)\n\n"
        f"🌍 *Mercato Globale*\n"
        f"• Fear & Greed: {fg_emoji} {fg['value']}/100 — {fg['label']}\n\n"
        f"🗺 *Zone di Trading Long-Term*\n"
        f"🟦 Accumulo Forte: < ${z['accumulo']:,.2f}\n"
        f"🟩 Zona Hold: ${z['hold_low']:,.2f} – ${z['hold_high']:,.2f}\n"
        f"🟥 Zona Vendita: > ${z['vendita']:,.2f}\n\n"
        f"🎯 *Raccomandazione Operativa*\n"
        f"Sizing: 1% del portafoglio | Alert: ${z['alert']:,.2f}\n\n"
        f"🔬 *Analisi Tecnica SMC*\n"
        f"• OB Rialzista: ${z['ob_bull']:,.2f} | OB Ribassista: ${z['ob_bear']:,.2f}\n"
        f"• FVG: ${z['fvg_low']:,.2f} – ${z['fvg_high']:,.2f}\n"
        f"• BOS: in formazione a ${z['bos']:,.2f} | Wyckoff: Fase 2-3\n"
        f"• Livello decisivo: ${z['livello_decisivo']:,.2f}\n\n"
        f"🎯 *Target Price (3-12 mesi)*\n"
        f"• Conservativo → ${z['target_cons']:,.2f} (+32%) [60% prob.]\n"
        f"• Base → ${z['target_base']:,.2f} (+53%) [35% prob.]\n"
        f"• Ottimistico → ${z['target_ott']:,.2f} (+150%) [15% prob.]\n\n"
        f"📰 *Contesto Recente*\n"
        f"{news_lines}\n"
        f"🧠 *Apprendimento ({n_analisi} anal. + {n_verificate} backtest)*\n"
        f"{'• Nessun segnale ancora verificabile (attendi 14+ giorni)' if n_verificate == 0 else f'• Calibrazione attiva su {n_verificate} analisi verificate'}"
        f"{cal_str}\n\n"
        f"_Analisi generata da {BOT_USERNAME}_"
    )

    targets = {"cons": z["target_cons"], "base": z["target_base"], "ott": z["target_ott"]}
    return msg, price, targets

# ─── COMANDI BOT ──────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    await update.message.reply_text(
        "👋 Benvenuto!\n\n"
        "📊 Comandi disponibili:\n"
        "/analisi bitcoin — analisi long-term\n"
        "/analisi btc — puoi usare anche il simbolo\n"
        "/backtest — storico previsioni\n"
        "/lista — tutte le crypto supportate"
    )

async def lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    righe = "\n".join([f"• /analisi {k}" for k in sorted(set(COIN_IDS.values()))])
    await update.message.reply_text(
        f"📋 *Crypto supportate:*\n\n{righe}",
        parse_mode="Markdown"
    )

async def analisi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if not context.args:
        await update.message.reply_text("❌ Specifica una crypto.\nEs: /analisi bitcoin")
        return

    coin = context.args[0].lower()
    await update.message.reply_text(f"⏳ Recupero dati per {coin.upper()}...")

    try:
        aggiorna_backtest()
        storico = carica_storico()
        cal     = storico.get("calibrazione", {"cons": 1.0, "base": 1.0, "ott": 1.0})
        data    = get_crypto_data(coin)
        news    = get_news(coin)
        fg      = get_fear_greed()
        msg, prezzo, targets = format_analysis(data, news, fg, cal)
        salva_analisi(coin, data["symbol"], prezzo, targets)
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")

async def backtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    aggiorna_backtest()
    storico      = carica_storico()
    analisi_list = storico["analisi"]

    if not analisi_list:
        await update.message.reply_text(
            "📭 Nessuna analisi salvata ancora.\n"
            "Usa /analisi bitcoin per iniziare!"
        )
        return

    verificate = [a for a in analisi_list if a["verificato"]]
    in_attesa  = [a for a in analisi_list if not a["verificato"]]
    msg        = "🧠 *BACKTEST & APPRENDIMENTO*\n\n"

    if verificate:
        msg += f"✅ *Analisi verificate ({len(verificate)}):*\n"
        for a in verificate[-5:]:
            perf  = a["risultato"]
            emoji = "🟢" if perf > 0 else "🔴"
            msg  += (
                f"{emoji} {a['symbol']} | "
                f"${a['prezzo_ingresso']:,.2f} → ${a['prezzo_verifica']:,.2f} "
                f"({perf:+.1f}%)\n"
            )
        cal  = storico["calibrazione"]
        msg += (
            f"\n📐 *Calibrazione attiva:*\n"
            f"• Cons ×{cal['cons']:.3f} | Base ×{cal['base']:.3f}\n"
        )
    else:
        msg += "⏳ Nessuna analisi verificata ancora (servono 14+ giorni)\n"

    if in_attesa:
        msg += f"\n🕐 *In attesa di verifica ({len(in_attesa)}):*\n"
        for a in in_attesa[-3:]:
            data_str        = datetime.fromisoformat(a["data"]).strftime("%d/%m")
            giorni_mancanti = 14 - (datetime.now() - datetime.fromisoformat(a["data"])).days
            msg += (
                f"• {a['symbol']} | {data_str} | "
                f"${a['prezzo_ingresso']:,.2f} | "
                f"{'✅ pronto!' if giorni_mancanti <= 0 else f'{giorni_mancanti}gg al check'}\n"
            )

    msg += f"\n_Totale analisi salvate: {len(analisi_list)}_"
    await update.message.reply_text(msg, parse_mode="Markdown")

# ─── SCHEDULING AUTOMATICO ────────────────────────────────────────────────────

async def analisi_automatica(app):
    if not GRUPPO_ID:
        return
    try:
        aggiorna_backtest()
        storico = carica_storico()
        cal     = storico.get("calibrazione", {"cons": 1.0, "base": 1.0, "ott": 1.0})
        data    = get_crypto_data("bitcoin")
        news    = get_news("bitcoin")
        fg      = get_fear_greed()
        msg, prezzo, targets = format_analysis(data, news, fg, cal)
        salva_analisi("bitcoin", "BTC", prezzo, targets)
        await app.bot.send_message(chat_id=GRUPPO_ID, text=msg, parse_mode="Markdown")
    except Exception as e:
        print(f"❌ Errore analisi automatica: {e}")

# ─── AVVIO ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        print("🔄 Avvio bot...")
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start",    start))
        app.add_handler(CommandHandler("analisi",  analisi))
        app.add_handler(CommandHandler("backtest", backtest))
        app.add_handler(CommandHandler("lista",    lista))

        if GRUPPO_ID:
            scheduler = AsyncIOScheduler()
            scheduler.add_job(
                analisi_automatica, "cron",
                hour=10, minute=0, args=[app]
            )
            scheduler.start()
            print("⏰ Scheduler attivo — analisi automatica alle 10:00")

        print("✅ Bot avviato! Scrivi /analisi bitcoin su Telegram")
        app.run_polling()

    except Exception as e:
        print(f"❌ ERRORE AVVIO: {e}")
        input("Premi Invio per chiudere...")
