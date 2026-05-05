"""
Link Dedup & Batcher — Telegram Bot
====================================
HTML tool এর exact same logic, Python এ port করা।

Usage:
  pip install python-telegram-bot
  BOT_TOKEN=xxx python link_dedup_bot.py

Commands:
  /start  — welcome message
  /help   — instructions
  (any text with links) → dedup + batch করে reply দেবে
"""

import re
import os
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    MessageReactionHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]  # Render dashboard এ set করো
BATCH_SIZE = 5  # প্রতিটা batch এ কতটা link


# ──────────────────────────────────────────────
# Core logic  (HTML tool এর JS থেকে port করা)
# ──────────────────────────────────────────────

def extract_links(text: str) -> list[str]:
    """Raw text থেকে x.com status links বের করে।"""
    # bare x.com/... → https://x.com/...
    text = re.sub(r'(?<![/\w])x\.com/', 'https://x.com/', text, flags=re.IGNORECASE)

    raw = re.findall(r'https?://x\.com/[^\s\]\[<>"\'()]+', text, re.IGNORECASE)

    results = []
    for u in raw:
        u = re.sub(r'[.,;!?]+$', '', u).strip()
        # Remove query params after status ID
        u = re.sub(r'(/status/\d+)\?[^\s]*', r'\1', u)

        # Format: /i/status/DIGITS
        mi = re.match(r'^(https?://x\.com/i/status/(\d+))', u)
        if mi:
            results.append(f"https://x.com/i/status/{mi.group(2)[:19]}")
            continue

        # Format: /USER/status/DIGITS
        m = re.match(r'^https?://x\.com/([A-Za-z0-9_.\-]+)/status/(\d+)', u)
        if m:
            results.append(f"https://x.com/{m.group(1)}/status/{m.group(2)[:19]}")

    return results


def dedup(links: list[str]) -> list[str]:
    """Status ID দিয়ে deduplicate করে।"""
    seen: dict[str, str] = {}
    for link in links:
        m = re.search(r'/status/(\d+)', link, re.IGNORECASE)
        key = f"sid:{m.group(1)}" if m else link.lower().strip()
        if key not in seen:
            seen[key] = link
    return list(seen.values())


def process(text: str) -> dict:
    all_links = extract_links(text)
    unique = dedup(all_links)
    dupes = len(all_links) - len(unique)
    batches = [unique[i:i + BATCH_SIZE] for i in range(0, len(unique), BATCH_SIZE)]
    return {
        "total": len(all_links),
        "dupes": dupes,
        "unique": len(unique),
        "batches": batches,
    }


# ──────────────────────────────────────────────
# Telegram handlers
# ──────────────────────────────────────────────

WELCOME = """👋 *Link Dedup & Batcher Bot*

x\.com লিংকগুলো এখানে paste করো ।
Bot duplicate বাদ দিয়ে ৫টা করে batch করে দেবে।

প্রতিটা batch আলাদা message এ আসবে — long\-press করে copy করো\!

/help — বিস্তারিত"""

HELP = """📖 *কীভাবে ব্যবহার করবে*

১\. যেকোনো text বা links paste করো
২\. Bot automatically extract, dedup ও batch করবে
৩\. প্রতিটা batch আলাদা message এ পাবে
৪\. Message টা long\-press করলে *Copy* option আসবে

*কী কী support করে:*
• `https://x.com/user/status/ID`
• `https://x.com/i/status/ID`
• `x.com/user/status/ID` \(https ছাড়াও\)
• Mixed text এর মাঝে থাকা links"""


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME, parse_mode="MarkdownV2")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP, parse_mode="MarkdownV2")


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    result = process(text)

    if not result["batches"]:
        await update.message.reply_text("❌ কোনো x.com status link পাওয়া যায়নি।")
        return

    summary = (
        f"✅ {result['total']} টা link পাওয়া গেছে\n"
        f"🗑 {result['dupes']} duplicate বাদ দেওয়া হয়েছে\n"
        f"🔗 {result['unique']} unique link → {len(result['batches'])} টা batch"
    )
    await update.message.reply_text(summary)

    for i, batch in enumerate(result["batches"], start=1):
        lines = "\n".join(batch)
        header = f"Batch {i}/{len(result['batches'])} \u2014 {len(batch)} link"
        def mdv2_escape(s):
            return re.sub(r'([_\*\[\]\(\)~`>#+\-=|{}.!\\])', r'\\\1', s)
        safe_header = mdv2_escape(header)
        msg = f"{safe_header}\n\n```\n{lines}\n```"
        await update.message.reply_text(msg, parse_mode="MarkdownV2")


async def handle_reaction(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reaction = update.message_reaction
    if not reaction:
        return
    if reaction.new_reaction:
        try:
            await ctx.bot.delete_message(
                chat_id=reaction.chat.id,
                message_id=reaction.message_id,
            )
        except Exception:
            pass


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageReactionHandler(handle_reaction))
    logging.info("Bot চালু হচ্ছে...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
