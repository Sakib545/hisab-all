import asyncio
import hashlib
import logging
import html
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from config import (ADMIN_ID, AUTO_BACKUP_ENABLED, AUTO_BACKUP_HOUR, AUTO_BACKUP_MINUTE,
                    BACKUP_RETENTION, BACKUPS_DIR, BOT_TOKEN, DATA_DIR, DATABASE_PATH,
                    INCOMING_RESTORE_DIR, RECEIPTS_DIR, TIMEZONE)
from central_sync import sync_bank_snapshot, flush_pending_central
from database import (
    add_transaction,
    all_rows,
    complete_active_payment,
    set_active_payment_month,
    set_payment_month,
    delete_all_rows,
    delete_row,
    get_active_payment,
    init_db,
    list_payments,
    payment_by_code,
    rows_for_date,
    rows_for_month,
    rows_for_payment,
    search_rows,
    total_summary,
    update_parsed_fields,
    update_source_file,
    rows_needing_repair,
    update_transaction_repair,
    create_database_snapshot,
    validate_database_file,
    analytics_summary, get_transaction, log_activity, recent_activity, reopen_payment,
)
from excel_export import make_excel
from ocr_parser import extract_text, parse_receipt
from professional import make_pdf
from doctor import format_doctor_report, run_doctor
from maintenance import format_maintenance_report, run_maintenance
from disaster_recovery import analyze_backup, create_full_backup, inspect_backup, restore_full_backup
import nexa_bridge
from manual_entry import is_deposit_slip, looks_manual, parse_manual, slip_hints, to_transaction

TZ = ZoneInfo(TIMEZONE)
ALBUMS = {}
ALBUM_DELAY_SECONDS = 2.5
PAYMENTS_PER_PAGE = 8

MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["📊 Dashboard", "💳 Current Payment"],
        ["✍️ Manual Entry"],
        ["✅ Complete Payment", "↩️ Reopen Payment"],
        ["📅 Today", "🗓 This Month"],
        ["💰 Total", "📈 Analytics"],
        ["📊 Export Excel", "📄 Export PDF"],
        ["📚 Payments", "🧾 Receipt Viewer"],
        ["🔍 Search", "🗑 Delete"],
        ["🔧 Repair Receipts", "🧹 Delete All"],
        ["💾 Full Backup", "♻️ Restore Backup"],
        ["📦 Latest Backup", "🩺 System Doctor"],
        ["🛠 Maintenance", "📜 Activity Log"],
    ], resize_keyboard=True, is_persistent=True,
)


async def guard(update):
    if not ADMIN_ID or (update.effective_user and update.effective_user.id == ADMIN_ID):
        return True
    if update.effective_message:
        await update.effective_message.reply_text("⛔ Not authorized.")
    return False


def _money(value):
    return f"৳{float(value or 0):,.2f}"


def preview(data, payment_code):
    return "\n".join(
        [
            "<b>✅ Receipt automatically saved</b>",
            "",
            f"<b>Payment:</b> {html.escape(payment_code)}",
            f"<b>Account:</b> {html.escape(data['account_number'])}",
            f"<b>Amount:</b> {_money(data['amount'])}",
            f"<b>Date:</b> {html.escape(data['transaction_date'])}",
            f"<b>Time:</b> {html.escape(data['transaction_time'])}",
        ]
    )


def report(rows, title):
    if not rows:
        return f"<b>{html.escape(title)}</b>\nNo transactions found."
    total = sum(float(row["amount"] or 0) for row in rows)
    lines = [f"<b>{html.escape(title)}</b>", f"Count: {len(rows)}", f"Total: {_money(total)}", ""]
    for row in rows[:50]:
        payment_code = row["payment_code"] if "payment_code" in row.keys() else ""
        prefix = f"{payment_code} • " if payment_code else ""
        lines.append(
            f"{prefix}{html.escape(row['transaction_date'])} "
            f"{html.escape(row['transaction_time'])}\n"
            f"{html.escape(row['account_number'])} • {_money(row['amount'])}"
        )
    if len(rows) > 50:
        lines.append(f"\nShowing latest 50 of {len(rows)} records.")
    return "\n\n".join(lines)


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def download_and_parse(message):
    photo_obj = message.photo[-1]
    telegram_file = await photo_obj.get_file()
    inbox_dir = RECEIPTS_DIR / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    name = f"{message.chat.id}_{message.from_user.id}_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S_%f')}.jpg"
    path = inbox_dir / name
    await telegram_file.download_to_drive(custom_path=path)
    data = parse_receipt(extract_text(path))
    data["source_file"] = str(path)
    data["receipt_hash"] = file_hash(path)
    data["telegram_file_id"] = photo_obj.file_id
    data["telegram_file_unique_id"] = photo_obj.file_unique_id
    return data


def archive_saved_receipt(source_path, payment_code, row_id):
    source = Path(source_path)
    target_dir = RECEIPTS_DIR / payment_code
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower() or ".jpg"
    target = target_dir / f"receipt_{row_id:06d}{suffix}"
    if source.resolve() != target.resolve():
        shutil.move(str(source), str(target))
    return target


def archive_failed_receipt(source_path):
    source = Path(source_path)
    if not source.exists():
        return source
    target_dir = RECEIPTS_DIR / "review"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    if source.resolve() != target.resolve():
        shutil.move(str(source), str(target))
    return target


async def start(update, context):
    if await guard(update):
        active = get_active_payment()
        await update.effective_message.reply_text(
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🏦 BURAQ DOLLER PAYMENT\n\n"
            f"🟢 Running Payment: {active['payment_code']}\n"
            f"📅 Payment Month: {active['payment_month']}\n"
            f"💰 Total: {_money(active['total_amount'])}\n"
            f"📄 Receipts: {active['transaction_count']}\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Pubali অথবা IFIC receipt পাঠান। নতুন receipt duplicate না হলে auto-save হবে।",
            reply_markup=MAIN_MENU,
        )


def invalid_message(data):
    missing = ", ".join(data.get("missing_fields") or ["unknown fields"])
    return (
        "❌ Receipt save করা হয়নি।\n"
        f"সমস্যা: {missing}\n\n"
        "শুধু পরিষ্কার Pubali অথবা IFIC receipt দিন। Date, Time, Account ও Amount detect হওয়া আবশ্যক।"
    )


async def process_album(media_group_id):
    await asyncio.sleep(ALBUM_DELAY_SECONDS)
    album = ALBUMS.pop(media_group_id, None)
    if not album:
        return
    messages, reply_message = album["messages"], album["reply_message"]
    status = await reply_message.reply_text(f"🔎 Processing {len(messages)} receipts...")
    saved = duplicates = failed = 0
    total_amount = 0.0
    payment_code = get_active_payment()["payment_code"]
    for index, message in enumerate(messages, 1):
        try:
            data = await download_and_parse(message)
            if not data.get("is_valid"):
                archive_failed_receipt(data.get("source_file", ""))
                failed += 1
                continue
            ok, row_id, payment_code = add_transaction(data)
            if ok:
                archived = archive_saved_receipt(data["source_file"], payment_code, row_id)
                update_source_file(row_id, archived)
                saved += 1
                total_amount += float(data["amount"])
                try:
                    await asyncio.to_thread(sync_bank_snapshot)
                except Exception:
                    logging.exception("Central bank auto-sync failed")
            else:
                Path(data.get("source_file", "")).unlink(missing_ok=True)
                duplicates += 1
        except Exception:
            failed += 1
        if index % 5 == 0 and index < len(messages):
            await status.edit_text(f"🔎 Processing {index}/{len(messages)} receipts...")
    await status.edit_text(
        f"✅ Album complete — {payment_code}\n\nTotal images: {len(messages)}\n"
        f"Saved: {saved}\nDuplicate: {duplicates}\nFailed/date or field missing: {failed}\n"
        f"Saved total: {_money(total_amount)}"
        + ("\n\n✍️ যেগুলো পড়া যায়নি (যেমন হাতে লেখা deposit slip) সেগুলো একটা একটা করে পাঠান — bot amount জিজ্ঞেস করবে।" if failed else "")
    )


async def photo(update, context):
    if not await guard(update):
        return
    message = update.effective_message
    if message.media_group_id:
        group_id = message.media_group_id
        if group_id not in ALBUMS:
            ALBUMS[group_id] = {"messages": [], "file_ids": set(), "reply_message": message}
            asyncio.create_task(process_album(group_id))
        unique_id = message.photo[-1].file_unique_id
        if unique_id not in ALBUMS[group_id]["file_ids"]:
            ALBUMS[group_id]["file_ids"].add(unique_id)
            ALBUMS[group_id]["messages"].append(message)
        return

    status = await message.reply_text("🔎 Reading receipt...")
    try:
        data = await download_and_parse(message)
        if not data.get("is_valid"):
            slip = is_deposit_slip(data.get("raw_text", ""))
            context.user_data["pending_slip"] = {
                "path": data.get("source_file", ""), "hash": data.get("receipt_hash", ""), "slip": slip,
                "hints": slip_hints(data.get("raw_text", "")),
                "telegram_file_id": data.get("telegram_file_id", ""), "telegram_file_unique_id": data.get("telegram_file_unique_id", ""),
            }
            context.user_data.pop("pending_manual", None)
            await status.edit_text(slip_prompt(context.user_data["pending_slip"], data), parse_mode=ParseMode.HTML)
            return
        ok, row_id, payment_code = add_transaction(data)
        if ok:
            archived = archive_saved_receipt(data["source_file"], payment_code, row_id)
            update_source_file(row_id, archived)
            try:
                await asyncio.to_thread(sync_bank_snapshot)
            except Exception:
                logging.exception("Central bank auto-sync failed")
            await status.edit_text(
                preview(data, payment_code) + f"\n<b>Transaction ID:</b> {row_id}",
                parse_mode=ParseMode.HTML,
            )
        else:
            Path(data.get("source_file", "")).unlink(missing_ok=True)
            await status.edit_text("⚠️ এই receipt আগে save করা হয়েছে। Duplicate add হয়নি।")
    except Exception as exc:
        await status.edit_text(f"❌ Could not read receipt: {exc}")


async def currentpayment(update, context):
    if not await guard(update):
        return
    payment = get_active_payment()
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📊 Export this payment", callback_data=f"export:{payment['payment_code']}")]]
    )
    await update.effective_message.reply_text(
        f"💳 Current Payment: {payment['payment_code']}\n"
        f"Receipts: {payment['transaction_count']}\nTotal: {_money(payment['total_amount'])}",
        reply_markup=keyboard,
    )


async def completepayment(update, context):
    if not await guard(update):
        return
    payment = get_active_payment()
    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✅ Complete & Start New", callback_data="complete_payment_confirm"),
            InlineKeyboardButton("Cancel", callback_data="complete_payment_cancel"),
        ]]
    )
    await update.effective_message.reply_text(
        f"⚠️ এই payment শেষ করবেন?\n\nPayment: {payment['payment_code']}\n"
        f"Receipts: {payment['transaction_count']}\nTotal: {_money(payment['total_amount'])}",
        reply_markup=keyboard,
    )


def _payment_page(page, mode):
    payments_list = list_payments()
    page_count = max(1, (len(payments_list) + PAYMENTS_PER_PAGE - 1) // PAYMENTS_PER_PAGE)
    page = max(0, min(page, page_count - 1))
    start_index = page * PAYMENTS_PER_PAGE
    subset = payments_list[start_index : start_index + PAYMENTS_PER_PAGE]

    if mode == "export":
        title = "📊 কোন Payment-এর Excel চান?"
        rows = [
            [
                InlineKeyboardButton(
                    f"{'🟢' if item['status'] == 'ACTIVE' else '✅'} {item['payment_code']} • "
                    f"{item['transaction_count']} • {_money(item['total_amount'])}",
                    callback_data=f"export:{item['payment_code']}",
                )
            ]
            for item in subset
        ]
        rows.append([InlineKeyboardButton("📚 All Payments", callback_data="export:ALL")])
        page_prefix = "export_page"
    else:
        title = "📚 Payment History"
        rows = [
            [
                InlineKeyboardButton(
                    f"{'🟢' if item['status'] == 'ACTIVE' else '✅'} {item['payment_code']} • "
                    f"{item['transaction_count']} • {_money(item['total_amount'])}",
                    callback_data=f"payment:{item['payment_code']}",
                )
            ]
            for item in subset
        ]
        page_prefix = "payments_page"

    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"{page_prefix}:{page - 1}"))
    if page < page_count - 1:
        navigation.append(InlineKeyboardButton("Next ➡️", callback_data=f"{page_prefix}:{page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton("❌ Close", callback_data="close_menu")])
    return f"{title}\nPage {page + 1}/{page_count}", InlineKeyboardMarkup(rows)


async def show_export_menu(message, page=0, edit_query=None):
    text, keyboard = _payment_page(page, "export")
    if edit_query:
        await edit_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await message.reply_text(text, reply_markup=keyboard)


async def show_payments_menu(message, page=0, edit_query=None):
    text, keyboard = _payment_page(page, "payments")
    if edit_query:
        await edit_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await message.reply_text(text, reply_markup=keyboard)


async def payments(update, context):
    if await guard(update):
        await show_payments_menu(update.effective_message)


async def payment(update, context):
    if not await guard(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Usage: /payment BP-0001")
        return
    await send_payment_details(update.effective_message, context.args[0].upper())


async def send_payment_details(message, code, edit_query=None):
    payment_info = payment_by_code(code)
    if not payment_info:
        text = "Payment ID পাওয়া যায়নি।"
        if edit_query:
            await edit_query.edit_message_text(text)
        else:
            await message.reply_text(text)
        return
    status_icon = "🟢 Running" if payment_info["status"] == "ACTIVE" else "✅ Completed"
    text = (
        f"<b>{html.escape(payment_info['payment_code'])}</b>\n"
        f"Status: {status_icon}\n"
        f"Receipts: {payment_info['transaction_count']}\n"
        f"Total: {_money(payment_info['total_amount'])}\n"
        f"Started: {html.escape((payment_info['started_at'] or '')[:10])}\n"
        f"Completed: {html.escape((payment_info['completed_at'] or '')[:10] or '—')}"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📊 Export Excel", callback_data=f"export:{payment_info['payment_code']}")],
            [InlineKeyboardButton("📋 Show transactions", callback_data=f"payment_rows:{payment_info['payment_code']}")],
            [InlineKeyboardButton("⬅️ Payment History", callback_data="payments_page:0")],
        ]
    )
    if edit_query:
        await edit_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    else:
        await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def _repair_one_row(row, context):
    # Path("") becomes the current directory ("."), which exists but is not an image.
    # Treat an empty/invalid source_file as missing and try Telegram file recovery instead.
    source_file = (row["source_file"] or "").strip()
    path = Path(source_file) if source_file else None

    if (path is None or not path.is_file()) and row["telegram_file_id"]:
        repair_dir = RECEIPTS_DIR / (row["payment_code"] or "recovered")
        repair_dir.mkdir(parents=True, exist_ok=True)
        path = repair_dir / f"receipt_{row['id']:06d}.jpg"
        telegram_file = await context.bot.get_file(row["telegram_file_id"])
        await telegram_file.download_to_drive(custom_path=path)

    if path is None or not path.is_file():
        return "missing_image"
    parsed = parse_receipt(await asyncio.to_thread(extract_text, path))
    parsed["raw_text"] = parsed.get("raw_text") or ""
    if not (parsed.get("transaction_date") or parsed.get("transaction_time") or parsed.get("account_number")):
        return "not_detected"
    update_transaction_repair(row["id"], parsed, path)
    fresh_missing = [
        not (parsed.get("transaction_date") or row["transaction_date"]),
        not (parsed.get("transaction_time") or row["transaction_time"]),
        not (parsed.get("account_number") or row["account_number"]),
    ]
    return "updated" if not any(fresh_missing) else "partial"


async def repair_missing(context, status_message=None):
    rows = rows_needing_repair()
    result = {"total": len(rows), "updated": 0, "partial": 0, "not_detected": 0, "missing_image": 0, "errors": 0}
    for index, row in enumerate(rows, 1):
        try:
            state = await _repair_one_row(row, context)
            result[state] += 1
        except Exception as exc:
            result["errors"] += 1
            print(f"Repair error for transaction {row['id']}: {type(exc).__name__}: {exc}")
        if status_message and index % 5 == 0 and index < len(rows):
            await status_message.edit_text(f"🔧 Repairing receipts... {index}/{len(rows)}")
    return result


async def send_excel(message, context, payment_code=None, status_message=None):
    missing_before = len(rows_needing_repair())
    if missing_before:
        if status_message:
            await status_message.edit_text(f"🔧 Repairing {missing_before} incomplete receipts before export...")
        await repair_missing(context, status_message)
    rows = all_rows() if payment_code is None else rows_for_payment(payment_code)
    label = "All Payments" if payment_code is None else payment_code
    if not rows:
        if status_message:
            await status_message.edit_text(f"{label}-এ কোনো record নেই।")
        else:
            await message.reply_text(f"{label}-এ কোনো record নেই।")
        return
    try:
        path = await asyncio.to_thread(make_excel, rows, payment_code)
        if status_message:
            await status_message.edit_text(f"✅ {label} Excel ready. Sending file...")
        with path.open("rb") as file_obj:
            await message.reply_document(file_obj, filename=path.name, caption=f"📊 {label} • {len(rows)} receipts")
        if status_message:
            await status_message.delete()
    except Exception as exc:
        error_text = f"❌ Excel export failed: {exc}"
        if status_message:
            await status_message.edit_text(error_text)
        else:
            await message.reply_text(error_text)


async def exportpayment(update, context):
    if not await guard(update):
        return
    if not context.args:
        await show_export_menu(update.effective_message)
        return
    code = context.args[0].upper()
    status = await update.effective_message.reply_text(f"⏳ Creating {code} Excel...")
    await send_excel(update.effective_message, context, code, status)


async def exportall(update, context):
    if not await guard(update):
        return
    status = await update.effective_message.reply_text("⏳ Creating All Payments Excel...")
    await send_excel(update.effective_message, context, None, status)


async def callback(update, context):
    query = update.callback_query
    await query.answer()
    if not await guard(update):
        return
    data = query.data or ""

    if data in {"manual_save", "manual_cancel"}:
        await manual_callback(query, context, data)
        return
    if data == "full_restore_cancel":
        pending = context.user_data.pop("pending_restore", None)
        if pending:
            Path(pending).unlink(missing_ok=True)
        await query.edit_message_text("Restore cancelled.")
        return
    elif data in {"full_restore_confirm", "full_restore_force"}:
        pending = context.user_data.pop("pending_restore", None)
        expected_recovery_id = context.user_data.pop("pending_restore_id", None)
        if not pending or not Path(pending).is_file():
            await query.edit_message_text("❌ Pending backup পাওয়া যায়নি। ZIP আবার upload করুন।")
            return
        await query.edit_message_text("🛡 Safety backup তৈরি করে Smart Restore শুরু হচ্ছে...")
        try:
            fresh_analysis = await asyncio.to_thread(analyze_backup, Path(pending))
            if expected_recovery_id and fresh_analysis["manifest"].get("recovery_id") != expected_recovery_id:
                raise ValueError("Backup changed after verification")
            if fresh_analysis["is_older_or_smaller"] and data != "full_restore_force":
                context.user_data["pending_restore"] = pending
                context.user_data["pending_restore_id"] = fresh_analysis["manifest"].get("recovery_id")
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("⚠️ Restore Anyway", callback_data="full_restore_force"),
                    InlineKeyboardButton("❌ Cancel", callback_data="full_restore_cancel"),
                ]])
                await query.edit_message_text(
                    "⚠️ পুরোনো/ছোট backup warning আবার নিশ্চিত করুন।\n\n"
                    + "\n".join(f"• {item}" for item in fresh_analysis["warnings"]),
                    reply_markup=keyboard,
                )
                return
            manifest, safety, verification = await asyncio.to_thread(restore_full_backup, Path(pending))
            init_db()
            Path(pending).unlink(missing_ok=True)
            log_activity("FULL_RESTORE", manifest["recovery_id"])
            await query.edit_message_text(
                "✅ Zero-Touch Restore Complete\n\n"
                f"Recovery ID: {manifest['recovery_id']}\n"
                f"Receipts restored: {manifest['receipts']}\n"
                f"Exports restored: {manifest['exports']}\n"
                f"Safety backup: {safety.name}\n"
                f"Verified transactions: {verification['database']['transactions']}\n"
                f"Verified receipts: {verification['receipts']}\n\n"
                "Database integrity ও restore count verification সফল হয়েছে।"
            )
        except Exception as exc:
            await query.edit_message_text(f"❌ Restore failed: {type(exc).__name__}: {exc}")
        return

    if data == "complete_payment_cancel":
        await query.edit_message_text("Payment complete cancelled.")
    elif data == "complete_payment_confirm":
        old, new = complete_active_payment()
        log_activity("COMPLETE_PAYMENT", f"{old['payment_code']} -> {new['payment_code']}")
        await query.edit_message_text(
            f"✅ {old['payment_code']} complete হয়েছে।\n"
            f"Payment Month: {old['payment_month']}\n"
            f"Receipts: {old['transaction_count']}\n"
            f"Previous total: {_money(old['total_amount'])}\n\n"
            f"এখন থেকে সব নতুন receipt যুক্ত হবে: {new['payment_code']}\n"
            f"New Payment Month: {new['payment_month']}"
        )
    elif data == "delete_all_cancel":
        await query.edit_message_text("Delete all cancelled.")
    elif data == "delete_all_confirm":
        count=delete_all_rows()
        try:
            await asyncio.to_thread(sync_bank_snapshot)
        except Exception:
            logging.exception("Central bank sync after delete-all failed")
        await query.edit_message_text(f"✅ Deleted {count} transactions.")
    elif data == "close_menu":
        await query.edit_message_text("Menu closed.")
    elif data.startswith("export_page:"):
        await show_export_menu(query.message, int(data.split(":", 1)[1]), query)
    elif data.startswith("payments_page:"):
        await show_payments_menu(query.message, int(data.split(":", 1)[1]), query)
    elif data.startswith("export:"):
        code = data.split(":", 1)[1].upper()
        await query.edit_message_text(f"⏳ Creating {'All Payments' if code == 'ALL' else code} Excel...")
        await send_excel(query.message, context, None if code == "ALL" else code, query.message)
    elif data.startswith("payment_rows:"):
        code = data.split(":", 1)[1].upper()
        await query.edit_message_text(report(rows_for_payment(code), code), parse_mode=ParseMode.HTML)
    elif data.startswith("payment:"):
        code = data.split(":", 1)[1].upper()
        await send_payment_details(query.message, code, query)


async def today(update, context):
    if await guard(update):
        day = datetime.now(TZ).date().isoformat()
        await update.effective_message.reply_text(
            report(rows_for_date(day), f"Today — {day}"), parse_mode=ParseMode.HTML
        )


async def month(update, context):
    if await guard(update):
        month_key = datetime.now(TZ).strftime("%Y-%m")
        await update.effective_message.reply_text(
            report(rows_for_month(month_key), f"Month — {month_key}"), parse_mode=ParseMode.HTML
        )


async def total(update, context):
    if await guard(update):
        count, amount = total_summary()
        await update.effective_message.reply_text(f"Transactions: {count}\nTotal: {_money(amount)}")


async def search(update, context):
    if not await guard(update):
        return
    term = " ".join(context.args).strip()
    if not term:
        await update.effective_message.reply_text("Usage: /search account/date/amount/BP-0001")
        return
    await update.effective_message.reply_text(
        report(search_rows(term), f"Search — {term}"), parse_mode=ParseMode.HTML
    )


async def export(update, context):
    if await guard(update):
        await show_export_menu(update.effective_message)


async def delete(update, context):
    if not await guard(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /delete ID")
        return
    deleted = delete_row(int(context.args[0]))
    if deleted:
        try:
            await asyncio.to_thread(sync_bank_snapshot)
        except Exception:
            logging.exception("Central bank sync after delete failed")
    await update.effective_message.reply_text("✅ Deleted." if deleted else "❌ ID not found.")


async def deleteall(update, context):
    if not await guard(update):
        return
    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("⚠️ Yes, delete everything", callback_data="delete_all_confirm"),
            InlineKeyboardButton("Cancel", callback_data="delete_all_cancel"),
        ]]
    )
    await update.effective_message.reply_text(
        "⚠️ সব transaction permanently delete হবে। Continue?", reply_markup=keyboard
    )


async def repairreceipts(update, context):
    if not await guard(update):
        return
    count = len(rows_needing_repair())
    if not count:
        await update.effective_message.reply_text("✅ কোনো incomplete receipt নেই। সব Date, Time ও Account পূর্ণ আছে।")
        return
    status = await update.effective_message.reply_text(f"🔧 Repairing {count} receipts...")
    result = await repair_missing(context, status)
    await status.edit_text(
        "✅ Repair complete\n\n"
        f"Checked: {result['total']}\n"
        f"Fully repaired: {result['updated']}\n"
        f"Partially repaired: {result['partial']}\n"
        f"Image not found: {result['missing_image']}\n"
        f"Still not detected: {result['not_detected']}\n"
        f"Errors: {result['errors']}"
    )


async def repairdates(update, context):
    await repairreceipts(update, context)


async def create_backup_archive():
    """Compatibility wrapper used by older code and safety restore."""
    path, _ = await asyncio.to_thread(create_full_backup, BACKUP_RETENTION)
    return path


async def _send_backup(message, automatic=False):
    status = None if automatic else await message.reply_text("💾 Full disaster-recovery backup তৈরি হচ্ছে...")
    try:
        archive_path, manifest = await asyncio.to_thread(create_full_backup, BACKUP_RETENTION)
        caption = (
            "✅ Zero-Touch Full Backup Ready\n\n"
            f"Recovery ID: {manifest['recovery_id']}\n"
            f"Source files: {manifest['source_files']}\n"
            f"Receipts: {manifest['receipts']}\n"
            f"Exports: {manifest['exports']}\n\n"
            "Database, receipts, reports, logs এবং recovery source included. "
            "Security-এর জন্য .env/BOT_TOKEN included নয়।"
        )
        with archive_path.open("rb") as backup_file:
            await message.reply_document(document=backup_file, filename=archive_path.name, caption=caption)
        if status:
            await status.delete()
        log_activity("FULL_BACKUP", manifest["recovery_id"])
        return archive_path
    except Exception as exc:
        text = f"❌ Full backup failed: {type(exc).__name__}: {exc}"
        if status:
            await status.edit_text(text)
        else:
            await message.reply_text(text)
        return None


async def backup(update, context):
    if await guard(update):
        await _send_backup(update.effective_message)


async def latestbackup(update, context):
    if not await guard(update):
        return
    backups = sorted(BACKUPS_DIR.glob("BankTrackerBot_Full_Backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        await _send_backup(update.effective_message)
        return
    path = backups[0]
    with path.open("rb") as stream:
        await update.effective_message.reply_document(document=stream, filename=path.name, caption="📦 Latest verified full backup")


async def restore(update, context):
    if not await guard(update):
        return
    await update.effective_message.reply_text(
        "♻️ Full Backup ZIP-টি এখানে document হিসেবে পাঠান।\n\n"
        "Bot নিজে backup detect ও verify করে Restore/Cancel button দেখাবে—caption বা command লাগবে না।"
    )


async def restore_document(update, context):
    if not await guard(update):
        return
    message = update.effective_message
    document = message.document
    filename = (document.file_name or "").lower()
    if not filename.endswith(".zip"):
        return
    status = await message.reply_text("📦 ZIP যাচাই করা হচ্ছে...")
    try:
        INCOMING_RESTORE_DIR.mkdir(parents=True, exist_ok=True)
        incoming = INCOMING_RESTORE_DIR / f"restore_{message.from_user.id}_{document.file_unique_id}.zip"
        telegram_file = await document.get_file()
        await telegram_file.download_to_drive(custom_path=incoming)
        analysis = await asyncio.to_thread(analyze_backup, incoming)
        manifest = analysis["manifest"]
        context.user_data["pending_restore"] = str(incoming)
        context.user_data["pending_restore_id"] = manifest["recovery_id"]
        risky = analysis["is_older_or_smaller"]
        confirm_text = "⚠️ Review & Restore" if risky else "✅ Restore Now"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(confirm_text, callback_data="full_restore_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="full_restore_cancel"),
        ]])
        warning_text = ""
        if analysis["warnings"]:
            warning_text = "\n⚠️ Smart Restore Warning\n" + "\n".join(f"• {item}" for item in analysis["warnings"]) + "\n"
        await status.edit_text(
            "📦 BankTrackerBot Smart Restore Analysis\n\n"
            f"Recovery ID: {manifest['recovery_id']}\n"
            f"Created: {manifest['created_at'][:19]}\n"
            "Integrity: ✅ PASSED\n\n"
            f"Current transactions: {analysis['current']['transactions']}\n"
            f"Backup transactions: {analysis['backup']['transactions']}\n"
            f"Current payments: {analysis['current']['payments']}\n"
            f"Backup payments: {analysis['backup']['payments']}\n"
            f"Backup receipts: {manifest['receipts']}\n"
            f"Backup exports: {manifest['exports']}\n"
            + warning_text +
            "\nRestore-এর আগে বর্তমান data-এর automatic safety backup তৈরি হবে।",
            reply_markup=keyboard,
        )
    except Exception as exc:
        await status.edit_text(f"❌ এই ZIP restore করা যাবে না: {type(exc).__name__}: {exc}")


async def automatic_daily_backup(context):
    if not ADMIN_ID:
        return
    try:
        await _send_backup(await context.bot.send_message(chat_id=ADMIN_ID, text="🌙 Daily automatic backup শুরু হয়েছে..."), automatic=True)
    except Exception as exc:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ Daily backup failed: {type(exc).__name__}: {exc}")




async def doctor(update, context):
    if not await guard(update):
        return
    status = await update.effective_message.reply_text("🩺 System scan চলছে...")
    try:
        result = await asyncio.to_thread(run_doctor)
        await status.edit_text(format_doctor_report(result))
        log_activity("SYSTEM_DOCTOR", f"health={result['score']}%")
    except Exception as exc:
        await status.edit_text(f"❌ System Doctor failed: {type(exc).__name__}: {exc}")

async def maintenance(update, context):
    if not await guard(update):
        return
    status = await update.effective_message.reply_text("🛠 Maintenance চলছে... Bot কিছুক্ষণ ধীর হতে পারে।")
    try:
        result = await asyncio.to_thread(run_maintenance)
        await status.edit_text(format_maintenance_report(result))
        log_activity("SYSTEM_MAINTENANCE", f"success={result['success']} failed={result['failed']}")
    except Exception as exc:
        await status.edit_text(f"❌ Maintenance failed: {type(exc).__name__}: {exc}")


async def automatic_weekly_maintenance(context):
    if not ADMIN_ID:
        return
    try:
        result = await asyncio.to_thread(run_maintenance)
        log_activity("AUTO_MAINTENANCE", f"success={result['success']} failed={result['failed']}")
        if result["failed"]:
            await context.bot.send_message(chat_id=ADMIN_ID, text=format_maintenance_report(result, automatic=True))
    except Exception as exc:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ Automatic maintenance failed: {type(exc).__name__}: {exc}")


async def dashboard(update, context):
    if not await guard(update): return
    active=get_active_payment(); count, amount=total_summary(); payments_list=list_payments()
    completed=sum(1 for p in payments_list if p['status']=='COMPLETED')
    await update.effective_message.reply_text(
        "📊 BURAQ PAYMENT DASHBOARD\n\n"
        f"🟢 Running: {active['payment_code']}\n"
        f"Current receipts: {active['transaction_count']}\n"
        f"Current total: {_money(active['total_amount'])}\n\n"
        f"All receipts: {count}\nAll amount: {_money(amount)}\n"
        f"Payments: {len(payments_list)}\nCompleted: {completed}"
    )

async def analytics(update, context):
    if not await guard(update): return
    totals, top, banks, payment_count=analytics_summary()
    lines=["📈 Analytics",f"Receipts: {totals['n']}",f"Total: {_money(totals['total'])}",f"Average: {_money(totals['avg'])}",f"Payments: {payment_count}","","Top receiver accounts:"]
    for r in top: lines.append(f"• {r['account_number']} — {r['n']} receipts — {_money(r['total'])}")
    lines.append("\nBank summary:")
    for r in banks: lines.append(f"• {r['bank_name']} — {r['n']} — {_money(r['total'])}")
    await update.effective_message.reply_text("\n".join(lines))

async def reopenpayment(update, context):
    if not await guard(update): return
    if not context.args:
        await update.effective_message.reply_text("Usage: /reopenpayment BP-0001")
        return
    ok, result=reopen_payment(context.args[0].upper())
    if ok:
        log_activity('REOPEN_PAYMENT', result)
        await update.effective_message.reply_text(f"✅ {result} আবার Running Payment হয়েছে।")
    else: await update.effective_message.reply_text(f"❌ {result}")

async def receiptviewer(update, context):
    if not await guard(update): return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /receipt 23\nExcel/transaction list-এর ID দিন।")
        return
    row=get_transaction(int(context.args[0]))
    if not row:
        await update.effective_message.reply_text("❌ Receipt ID পাওয়া যায়নি।")
        return
    p=Path(row['source_file'] or '')
    caption=f"🧾 Receipt #{row['id']}\nPayment: {row['payment_code']}\nAccount: {row['account_number']}\nAmount: {_money(row['amount'])}\nDate: {row['transaction_date']} {row['transaction_time']}"
    if p.is_file():
        with p.open('rb') as f: await update.effective_message.reply_photo(photo=f, caption=caption)
    elif row['telegram_file_id']:
        await update.effective_message.reply_photo(photo=row['telegram_file_id'], caption=caption)
    else: await update.effective_message.reply_text(caption+"\n\n⚠️ Original image পাওয়া যায়নি।")

async def pdfreport(update, context):
    if not await guard(update): return
    code=context.args[0].upper() if context.args else None
    rows=rows_for_payment(code) if code else all_rows()
    if not rows:
        await update.effective_message.reply_text("No transactions found.")
        return
    out=DATA_DIR / (f"{code or 'All_Payments'}_Report.pdf")
    make_pdf(rows,out,f"BURAQ DOLLER PAYMENT — {code or 'ALL PAYMENTS'}")
    with out.open('rb') as f: await update.effective_message.reply_document(document=f, filename=out.name)
    log_activity('EXPORT_PDF', code or 'ALL')

async def activitylog(update, context):
    if not await guard(update): return
    rows=recent_activity(30)
    if not rows:
        await update.effective_message.reply_text("Activity log empty.")
        return
    await update.effective_message.reply_text("📜 Recent Activity\n\n"+"\n".join(f"{r['created_at'][:19]} — {r['action']} — {r['details']}" for r in rows))

async def menu_actions(update, context):
    if not await guard(update):
        return
    text = (update.effective_message.text or "").strip()
    if text == "✍️ Manual Entry":
        await update.effective_message.reply_text(MANUAL_HELP, parse_mode=ParseMode.HTML)
        return
    if looks_manual(text):
        await manual_preview(update, context, text)
        return
    if text == "📊 Dashboard":
        await dashboard(update, context)
    elif text == "💳 Current Payment":
        await currentpayment(update, context)
    elif text == "✅ Complete Payment" or text.lower() in {"এই পেমেন্ট শেষ", "হিসাব শেষ", "payment complete"}:
        await completepayment(update, context)
    elif text == "↩️ Reopen Payment":
        await update.effective_message.reply_text("/reopenpayment BP-0001")
    elif text == "📚 Payments":
        await payments(update, context)
    elif text == "📅 Today":
        await today(update, context)
    elif text == "🗓 This Month":
        await month(update, context)
    elif text == "💰 Total":
        await total(update, context)
    elif text == "📈 Analytics":
        await analytics(update, context)
    elif text == "📊 Export Excel":
        await export(update, context)
    elif text == "📄 Export PDF":
        await update.effective_message.reply_text("সব payment PDF: /pdfreport\nনির্দিষ্ট payment: /pdfreport BP-0001")
    elif text == "🧾 Receipt Viewer":
        await update.effective_message.reply_text("/receipt 23")
    elif text == "🔍 Search":
        await update.effective_message.reply_text("/search account/date/amount/BP-0001")
    elif text == "🗑 Delete":
        await update.effective_message.reply_text("/delete ID")
    elif text == "🧹 Delete All":
        await deleteall(update, context)
    elif text == "🔧 Repair Receipts":
        await repairreceipts(update, context)
    elif text in {"💾 Backup", "💾 Full Backup"}:
        await backup(update, context)
    elif text == "♻️ Restore Backup":
        await restore(update, context)
    elif text == "📦 Latest Backup":
        await latestbackup(update, context)
    elif text == "📜 Activity Log":
        await activitylog(update, context)
    elif text == "🩺 System Doctor":
        await doctor(update, context)
    elif text == "🛠 Maintenance":
        await maintenance(update, context)



async def central_retry_loop():
    while True:
        await asyncio.sleep(300)
        try:
            await asyncio.to_thread(flush_pending_central)
        except Exception:
            logging.exception("Central pending retry failed")

async def central_backfill_post_init(application) -> None:
    """Upload existing rows and keep retrying pending Central snapshots."""
    asyncio.create_task(central_retry_loop())
    try:
        result = await asyncio.to_thread(sync_bank_snapshot)
        print(f"Central historical backfill complete: {result}")
    except Exception as exc:
        print(f"Central historical backfill failed: {type(exc).__name__}: {exc}")



async def set_active_month_command(update, context):
    if not await guard(update):
        return
    if not context.args:
        await update.effective_message.reply_text(
            "ব্যবহার: /set_payment_month 2026-07\n"
            "এটি বর্তমান Running Payment-এর accounting month বদলাবে।"
        )
        return
    try:
        code, month = await asyncio.to_thread(
            set_active_payment_month, context.args[0]
        )
        await asyncio.to_thread(sync_bank_snapshot)
        await update.effective_message.reply_text(
            f"✅ {code} Payment Month এখন {month}\n"
            "Central Sheet-ও update হয়েছে।"
        )
    except Exception as exc:
        await update.effective_message.reply_text(
            f"❌ Month update failed: {type(exc).__name__}: {exc}"
        )


async def set_cycle_month_command(update, context):
    if not await guard(update):
        return
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "ব্যবহার: /set_cycle_month BP-0001 2026-07"
        )
        return
    try:
        code, month = await asyncio.to_thread(
            set_payment_month, context.args[0], context.args[1]
        )
        await asyncio.to_thread(sync_bank_snapshot)
        await update.effective_message.reply_text(
            f"✅ {code} Payment Month এখন {month}"
        )
    except Exception as exc:
        await update.effective_message.reply_text(
            f"❌ Month update failed: {type(exc).__name__}: {exc}"
        )


async def central_sync_command(update, context):
    if update.effective_user and update.effective_user.id != ADMIN_ID:
        return
    message = await update.effective_message.reply_text("🔄 পুরোনো ও নতুন সব Dollar Payment Central-এ পাঠানো হচ্ছে…")
    try:
        result = await asyncio.to_thread(sync_bank_snapshot)
        await message.edit_text(
            "✅ BankTracker Central Sync সম্পন্ন\n"
            f"মোট Receipt: {result.get('synced', 0)}\n"
            f"মোট Amount: {_money(result.get('source_total', 0))}\n"
            f"Source DB: {result.get('source_path', '-')}"
        )
    except Exception as exc:
        await message.edit_text(f"❌ Central Sync failed: {type(exc).__name__}: {exc}")


def slip_prompt(pending, data=None):
    hints = pending.get("hints") or {}
    head = ("🧾 <b>Cash Deposit Slip পেয়েছি</b>\nহাতে লেখা amount/account ছবি থেকে নির্ভরযোগ্যভাবে পড়া যায় না।"
            if pending.get("slip") else
            "⚠️ <b>Receipt-টা পুরো পড়া যায়নি</b>" + (f"\nসমস্যা: {html.escape(', '.join(data.get('missing_fields') or []))}" if data else ""))
    found = []
    if hints.get("date"):
        found.append(f"তারিখ {hints['date']}")
    if hints.get("account"):
        found.append(f"Account {hints['account']}")
    lines = [head]
    if found:
        lines.append("ছবিতে পাওয়া গেছে: " + ", ".join(found) + " (নিশ্চিত হয়ে লিখুন)")
    lines += ["", "এখন <b>amount লিখে পাঠান</b> — ছবিটা receipt হিসেবে সাথে save হবে:",
              "<code>100000</code>", "চাইলে account, তারিখ, bank, নাম/নোট যোগ করুন:",
              "<code>100000 0220249853811 13/10/2026 IFIC</code>", "", "বাদ দিতে /cancel"]
    return "\n".join(lines)


MANUAL_HELP = (
    "✍️ <b>Manual Entry</b> — ছবি ছাড়া শুধু লিখে যোগ করুন।\n\n"
    "প্রথমে amount, বাকিগুলো ঐচ্ছিক (যেকোনো ক্রমে):\n"
    "<code>1000</code>\n"
    "<code>100000 0220249853811</code>\n"
    "<code>100000 0220249853811 13/10/2026 IFIC Rahim</code>\n\n"
    "তারিখ না দিলে আজকের তারিখ। Save করার আগে একবার নিশ্চিত করতে বলা হবে।\n"
    "হাতে লেখা deposit slip থাকলে আগে ছবি পাঠান, তারপর amount লিখুন।"
)


def _similar_count(tx):
    from database import connect
    with connect() as c:
        return c.execute(
            "SELECT COUNT(*) FROM transactions WHERE ABS(amount-?)<0.005 AND transaction_date=? AND (?='CASH' OR account_number=?)",
            (tx["amount"], tx["transaction_date"], tx["account_number"], tx["account_number"]),
        ).fetchone()[0]


async def manual_preview(update, context, text):
    pending = context.user_data.get("pending_slip")
    try:
        entry = parse_manual(text, datetime.now(TZ).date())
    except ValueError as exc:
        await update.effective_message.reply_text(f"❌ {exc}\n\nউদাহরণ: 100000 0220249853811 13/10/2026")
        return
    if pending and not entry["bank"]:
        entry["bank"] = (pending.get("hints") or {}).get("bank", "")
    tx = to_transaction(entry, slip=bool(pending and pending.get("slip")), now=datetime.now(TZ).replace(tzinfo=None))
    context.user_data["pending_manual"] = tx
    active = get_active_payment()
    lines = [
        "📝 <b>এভাবে save হবে — ঠিক আছে?</b>", "",
        f"<b>Payment:</b> {html.escape(active['payment_code'])}",
        f"<b>Amount:</b> {_money(tx['amount'])}",
        f"<b>Date:</b> {html.escape(tx['transaction_date'])}",
        f"<b>Account:</b> {html.escape(tx['account_number'])}",
        f"<b>Bank:</b> {html.escape(tx['bank_name'])}",
    ]
    if tx["receiver_name"]:
        lines.append(f"<b>নোট:</b> {html.escape(tx['receiver_name'])}")
    lines.append("🧾 ছবি: " + ("সাথে থাকবে" if pending else "নেই (manual)"))
    similar = await asyncio.to_thread(_similar_count, tx)
    if similar:
        lines += ["", f"⚠️ একই দিনে একই amount-এর {similar}টি entry আগে থেকেই আছে — duplicate কিনা দেখুন।"]
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Save", callback_data="manual_save"),
                                      InlineKeyboardButton("❌ Cancel", callback_data="manual_cancel")]])
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def manual_callback(query, context, action):
    tx = context.user_data.pop("pending_manual", None)
    pending = context.user_data.get("pending_slip")
    if action == "manual_cancel":
        await query.edit_message_text("বাদ দেওয়া হয়েছে।" + (" Slip-এর জন্য আবার amount লিখতে পারেন, অথবা /cancel।" if pending else ""))
        return
    if not tx:
        await query.edit_message_text("⏱ এই preview পুরনো — আবার লিখুন।")
        return
    if pending:
        tx.update(receipt_hash=pending.get("hash", ""), source_file=pending.get("path", ""),
                  telegram_file_id=pending.get("telegram_file_id", ""), telegram_file_unique_id=pending.get("telegram_file_unique_id", ""))
    ok, row_id, payment_code = await asyncio.to_thread(add_transaction, tx)
    context.user_data.pop("pending_slip", None)
    if not ok:
        await query.edit_message_text("⚠️ এই slip/receipt-এর ছবি আগেই save করা হয়েছে। Duplicate add হয়নি।")
        return
    if pending and pending.get("path") and Path(pending["path"]).is_file():
        archived = archive_saved_receipt(pending["path"], payment_code, row_id)
        update_source_file(row_id, archived)
    log_activity("MANUAL_ENTRY", f"{payment_code} #{row_id} {tx['amount']}" + (" slip" if pending else ""))
    try:
        await asyncio.to_thread(sync_bank_snapshot)
    except Exception:
        logging.exception("Central bank auto-sync failed")
    await query.edit_message_text(
        f"✅ <b>Save হয়েছে</b> — {html.escape(payment_code)}\n<b>Transaction ID:</b> {row_id}\n"
        f"<b>Amount:</b> {_money(tx['amount'])} · {html.escape(tx['transaction_date'])}",
        parse_mode=ParseMode.HTML,
    )


async def cancel_command(update, context):
    if not await guard(update):
        return
    pending = context.user_data.pop("pending_slip", None)
    context.user_data.pop("pending_manual", None)
    if pending and pending.get("path"):
        archive_failed_receipt(pending["path"])
    await update.effective_message.reply_text("বাদ দেওয়া হয়েছে।" if pending else "বাদ দেওয়ার মতো কিছু নেই।")


async def manual_command(update, context):
    if not await guard(update):
        return
    if context.args:
        await manual_preview(update, context, " ".join(context.args))
    else:
        await update.effective_message.reply_text(MANUAL_HELP, parse_mode=ParseMode.HTML)

async def nexa_job(context):
    """Site-এর কাজ চালায় ও data mirror করে; bot-এর কাজ আটকায় না।"""
    notes = await asyncio.to_thread(nexa_bridge.tick)
    if not ADMIN_ID:
        return
    for note in notes:
        try:
            if note.get("text"):
                await context.bot.send_message(chat_id=ADMIN_ID, text=note["text"])
            for path in note.get("documents", []):
                with open(path, "rb") as f:
                    await context.bot.send_document(chat_id=ADMIN_ID, document=f, filename=Path(path).name)
            for photo, caption in note.get("photos", []):
                if Path(photo).is_file():
                    with open(photo, "rb") as f:
                        await context.bot.send_photo(chat_id=ADMIN_ID, photo=f, caption=caption)
                else:
                    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo, caption=caption)
        except Exception:
            logging.exception("Nexa notification failed")


async def nexa_command(update, context):
    if not await guard(update):
        return
    status = await update.effective_message.reply_text("🔄 Nexa Hisab-এ সব data পাঠানো হচ্ছে…")
    result = await asyncio.to_thread(nexa_bridge.snapshot, True)
    text = await asyncio.to_thread(nexa_bridge.status_text)
    changed = sum(int((v or {}).get("changed", 0)) for v in result.values() if isinstance(v, dict))
    await status.edit_text(f"{text}\n\nএইবার পাঠানো: {changed}টি record")


def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).post_init(central_backfill_post_init).build()
    handlers = [
        ("start", start),
        ("help", start),
        ("today", today),
        ("month", month),
        ("total", total),
        ("search", search),
        ("export", export),
        ("exportall", exportall),
        ("delete", delete),
        ("deleteall", deleteall),
        ("repairdates", repairdates),
        ("repairreceipts", repairreceipts),
        ("backup", backup),
        ("fullbackup", backup),
        ("latestbackup", latestbackup),
        ("downloadbackup", latestbackup),
        ("restore", restore),
        ("currentpayment", currentpayment),
        ("completepayment", completepayment),
        ("payments", payments),
        ("payment", payment),
        ("exportpayment", exportpayment),
        ("dashboard", dashboard),
        ("analytics", analytics),
        ("reopenpayment", reopenpayment),
        ("receipt", receiptviewer),
        ("pdfreport", pdfreport),
        ("activitylog", activitylog),
        ("doctor", doctor),
        ("maintenance", maintenance),
        ("central_sync", central_sync_command),
        ("set_payment_month", set_active_month_command),
        ("set_cycle_month", set_cycle_month_command),
        ("nexa", nexa_command),
        ("add", manual_command),
        ("manual", manual_command),
        ("cancel", cancel_command),
    ]
    for name, handler in handlers:
        app.add_handler(CommandHandler(name, handler))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
    app.add_handler(MessageHandler(filters.Document.ALL, restore_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_actions))
    if app.job_queue and nexa_bridge.enabled():
        app.job_queue.run_repeating(nexa_job, interval=int(os.getenv("NEXA_INTERVAL", "20") or 20), first=10, name="nexa_hisab_sync")
    if AUTO_BACKUP_ENABLED and app.job_queue and ADMIN_ID:
        from datetime import time as dt_time
        app.job_queue.run_daily(
            automatic_daily_backup,
            time=dt_time(hour=AUTO_BACKUP_HOUR, minute=AUTO_BACKUP_MINUTE, tzinfo=TZ),
            name="daily_full_backup",
        )
    if app.job_queue and ADMIN_ID and os.getenv("AUTO_MAINTENANCE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}:
        from datetime import time as dt_time
        maintenance_hour = int(os.getenv("AUTO_MAINTENANCE_HOUR", "4") or 4)
        maintenance_minute = int(os.getenv("AUTO_MAINTENANCE_MINUTE", "0") or 0)
        maintenance_day = int(os.getenv("AUTO_MAINTENANCE_DAY", "6") or 6)  # Sunday=6
        app.job_queue.run_daily(
            automatic_weekly_maintenance,
            time=dt_time(hour=maintenance_hour, minute=maintenance_minute, tzinfo=TZ),
            days=(maintenance_day,),
            name="weekly_system_maintenance",
        )
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
