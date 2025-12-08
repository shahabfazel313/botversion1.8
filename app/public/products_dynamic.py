from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from . import router
from .channel_gate import ensure_member_for_message
from ..config import CURRENCY
from ..db import create_order, ensure_user, get_user
from ..keyboards import REPLY_BTN_PRODUCTS, ik_dynamic_products, ik_product_actions, reply_main
from ..products import find_public_product, list_public_children


def _format_price(amount: int) -> str:
    if amount <= 0:
        return "قیمت تنظیم نشده"
    return f"{amount:,} {CURRENCY}".replace(",", "،")


async def _show_root(message: Message) -> None:
    items = list_public_children()
    if not items:
        await message.answer("هیچ محصول فعالی ثبت نشده است.", reply_markup=reply_main())
        return
    await message.answer("به فروشگاه خوش آمدید. دسته مورد نظر را انتخاب کنید:", reply_markup=ik_dynamic_products(items))


@router.message(F.text == REPLY_BTN_PRODUCTS)
async def on_reply_products(message: Message, state: FSMContext) -> None:
    if not await ensure_member_for_message(message):
        return
    await _show_root(message)


@router.callback_query(F.data == "prod:root")
async def cb_products_root(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text("به فروشگاه خوش آمدید.")
    await callback.message.answer("منو:", reply_markup=ik_dynamic_products(list_public_children()))
    await callback.answer()


@router.callback_query(F.data.startswith("prod:open:"))
async def cb_open_category(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        target_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("درخواست نامعتبر است.", show_alert=True)
        return

    parent_id = target_id or None
    items = list_public_children(parent_id)
    if not items:
        await callback.answer("موردی یافت نشد.", show_alert=True)
        return

    back_parent = None
    if parent_id:
        parent = find_public_product(parent_id)
        title = parent.get("title") if parent else "دسته"
        back_parent = parent.get("parent_id") if parent else None
    else:
        title = "منو اصلی محصولات"
    await callback.message.edit_text(title, reply_markup=ik_dynamic_products(items, parent_id=back_parent))
    await callback.answer()


@router.callback_query(F.data.startswith("prod:view:"))
async def cb_view_product(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        product_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("درخواست نامعتبر است.", show_alert=True)
        return

    product = find_public_product(product_id)
    if not product or product.get("is_category"):
        await callback.answer("این گزینه در دسترس نیست.", show_alert=True)
        return

    description = (product.get("description") or "").strip()
    text = f"<b>{product.get('title')}</b>\n"
    if description:
        text += f"\n{description}\n"
    text += f"\n💰 قیمت: <b>{_format_price(product.get('price') or 0)}</b>"
    text += "\nبرای ادامه روی دکمهٔ زیر بزنید."
    await callback.message.edit_text(text, reply_markup=ik_product_actions(product_id, product.get("parent_id")))
    await callback.answer()


@router.callback_query(F.data.startswith("prod:buy:"))
async def cb_buy_product(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        product_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("درخواست نامعتبر است.", show_alert=True)
        return

    product = find_public_product(product_id)
    if not product or product.get("is_category"):
        await callback.answer("این مورد در دسترس نیست.", show_alert=True)
        return

    price = int(product.get("price") or 0)
    if price <= 0:
        await callback.message.answer("قیمت این سرویس هنوز تنظیم نشده است.", reply_markup=reply_main())
        await callback.answer()
        return

    ensure_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name or "")
    user = get_user(callback.from_user.id)
    order_id = create_order(
        user=user,
        title=product.get("title") or f"محصول #{product_id}",
        amount_total=price,
        currency=CURRENCY,
        service_category="CATALOG",
        service_code=f"product:{product_id}",
        account_mode="",
        customer_email=None,
        notes=product.get("description") or "",
    )
    await callback.message.answer(
        f"✅ سفارش #{order_id} برای «{product.get('title')}» ایجاد شد و به سبد خرید اضافه گردید.",
        reply_markup=reply_main(),
    )
    await callback.answer()
