import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message

API_ID = 21660803
API_HASH = "3fd70393aaf86af7f867c99fb792cdfa"
BOT_TOKEN = "7252666994:AAHYZdZlcDpbmexbU69t9bv_xmi8mQtKkZc"
BASE_URL = "https://www.ss.lv"
BRANDS_PER_PAGE = 12

brand_links = []
user_states = {}

sorting_options = {
    "date_desc":    "",
    "date_asc":     "fDgSeF4S.html",
    "brand_asc":    "fDgSeF4QFDwT.html",
    "brand_desc":   "fDgSeF4QFDwS.html",
    "year_asc":     "fDgSeF4SHTwT.html",
    "year_desc":    "fDgSeF4SHTwS.html",
    "volume_asc":   "fDgSeF4SEDwT.html",
    "volume_desc":  "fDgSeF4SEDwS.html",
    "mileage_asc":  "fDgSeF4SEzwT.html",
    "mileage_desc": "fDgSeF4SEzwS.html",
    "price_asc":    "fDgSeF4belM=.html",
    "price_desc":   "fDgSeF4belI=.html",
}
sorting_labels = {
    "date_desc":    "Date: Newest → Oldest",
    "date_asc":     "Date: Oldest → Newest",
    "brand_asc":    "Brand: A–Z",
    "brand_desc":   "Brand: Z–A",
    "year_asc":     "Year: ↑",
    "year_desc":    "Year: ↓",
    "volume_asc":   "Engine Volume: ↑",
    "volume_desc":  "Engine Volume: ↓",
    "mileage_asc":  "Mileage: ↑",
    "mileage_desc": "Mileage: ↓",
    "price_asc":    "Price: ↑",
    "price_desc":   "Price: ↓",
}

filter_labels = {
    "topt[8][min]": "Price Min",
    "topt[8][max]": "Price Max",
    "opt[15][min]": "Engine Volume Min",
    "opt[15][max]": "Engine Volume Max",
    "topt[15][min]": "Engine Volume Min",
    "topt[15][max]": "Engine Volume Max",
    "topt[18][min]": "Year From",
    "topt[18][max]": "Year To",
    "opt[32]": "Drive type",
    "opt[34]": "Fuel Type",
    "opt[35]": "Gearbox",
    "opt[17]": "Color",
    "opt[1]": "Model",
    "sid": "Bargain Type"
}

def fetch_brands():
    url = f"{BASE_URL}/lv/transport/cars/"
    resp = requests.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    brand_links = []
    pattern = re.compile(r"^/lv/transport/cars/[^/]+/$")
    for a in soup.select("h4 > a[href]"):
        href = a["href"]
        if pattern.match(href):
            name = a.text.strip()
            full_url = urljoin(BASE_URL, href)
            brand_links.append((name, full_url))
    print(f"Fetched {len(brand_links)} brands")
    return brand_links

def get_brand_keyboard(page: int = 1) -> InlineKeyboardMarkup:
    start = (page - 1) * BRANDS_PER_PAGE
    end = start + BRANDS_PER_PAGE
    buttons = []
    for idx, (name, href) in enumerate(brand_links[start:end], start=start):
        buttons.append(InlineKeyboardButton(name, callback_data=f"brand:{idx}"))
    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("Prev Page", callback_data=f"nav:prev:{page-1}"))
    if end < len(brand_links):
        nav.append(InlineKeyboardButton("Next Page", callback_data=f"nav:next:{page+1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(rows)

def get_sort_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(label, callback_data=f"sort:{key}")
        for key, label in sorting_labels.items()
    ]
    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton("Skip Sorting", callback_data="sort:skip")])
    return InlineKeyboardMarkup(rows)

def parse_filter_options(brand_href: str) -> dict:
    if brand_href == "all":
        url = f"{BASE_URL}/lv/transport/cars/"
    else:
        url = brand_href.rstrip("/") + "/filter/"
    resp = requests.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")
    opts = {}

    # Сначала select'ы как раньше
    for sel in soup.find_all("select"):
        name = sel.get("name")
        if not name:
            continue
        choices = []
        for opt in sel.find_all("option"):
            val = opt.get("value")
            if val is None or val == "":
                continue
            label = opt.text.strip()
            choices.append((val, label))
        if choices:
            opts[name] = choices

    # Добавляем поддержку input (например, цена)
    for inp in soup.find_all("input"):
        name = inp.get("name")
        if name and "topt[8]" in name:  # поля цены
            opts[name] = None  # просто помечаем, что поле доступно

    return opts

def labelize(name: str) -> str:
    return name.replace("_", " ").title()

def get_filter_keyboard(user_id: int) -> InlineKeyboardMarkup:
    state = user_states[user_id]
    opts = state["filter_options"]

    buttons = []
    for k in opts.keys():
        readable = filter_labels.get(k, k)  # читаемое имя или fallback
        buttons.append(InlineKeyboardButton(readable, callback_data=f"filter_sel:{k}"))

    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    rows.append([
        InlineKeyboardButton("Apply Filters", callback_data="apply"),
        InlineKeyboardButton("Reset Filters", callback_data="reset"),
    ])
    return InlineKeyboardMarkup(rows)

def get_filter_values_keyboard(field: str, user_id: int) -> InlineKeyboardMarkup:
    opts = user_states[user_id]["filter_options"][field]

    # Если это числовое поле (например, цена)
    if opts is None:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Enter Value", callback_data=f"numeric_input:{field}")],
            [InlineKeyboardButton("← Back", callback_data="filter_back")]
        ])

    # Обычные поля (select)
    buttons = [
        InlineKeyboardButton(label, callback_data=f"filter_val:{field}:{val}")
        for val, label in opts
    ]
    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton("← Back", callback_data="filter_back")])
    return InlineKeyboardMarkup(rows)

def format_user_selection(user_id: int) -> str:
    state = user_states[user_id]
    lines = []

    # Бренд
    if state["brand_href"] == "all":
        lines.append("🚗 Brand: All")
    else:
        for name, href in brand_links:
            if href == state["brand_href"]:
                lines.append(f"🚗 Brand: {name}")
                break

    # Сортировка
    sort_key = state.get("sort", "date_desc")
    sort_label = sorting_labels.get(sort_key, "Unknown")
    lines.append(f"🔃 Sort: {sort_label}")

    # Фильтры
    filters = state.get("filters", {})
    if filters:
        lines.append("🎛 Filters:")
        opts = state["filter_options"]
        for key, val in filters.items():
            label = filter_labels.get(key, labelize(key))  # ← заменено здесь
            opt_values = opts.get(key)
            if opt_values is None:
                value_label = val  # просто отобразим введённое число
            else:
                value_label = next((lbl for v, lbl in opt_values if v == val), val)
            lines.append(f" • {label}: {value_label}")
    else:
        lines.append("🎛 Filters: None")

    return "\n".join(lines)

def fetch_results(state: dict) -> list:
    if state["brand_href"] == "all":
        base = f"{BASE_URL}/lv/transport/cars/filter/"
    else:
        base = state["brand_href"].rstrip("/") + "/filter/"

    suffix = sorting_options.get(state.get("sort", "date_desc"), "")
    url = base + suffix
    session = requests.Session()
    filters = state.get("filters", {})

    if filters:
        post_resp = session.post(base, data=filters)
        post_resp.raise_for_status()

    resp = session.get(url)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    for row in soup.select("tr[id^=tr_]")[:10]:
        cols = row.find_all("td")
        title_tag = row.select_one("a.am")
        link = urljoin(BASE_URL, title_tag['href']) if title_tag else "#"

        brand = "Audi"
        model = cols[3].text.strip() if len(cols) > 3 else "Unknown"
        year = cols[4].text.strip() if len(cols) > 4 else "Unknown"
        mileage = cols[6].text.strip() if len(cols) > 6 else None
        price_td = cols[7].get_text(strip=True) if len(cols) > 7 else "Unknown"
        price = price_td.replace('\xa0', ' ').strip()

        # Формат: Audi A6 - 2006 - 306 tūkst. - 2,450 €
        if mileage:
            full_title = f"{brand} {model} - {year} - {mileage} - {price}"
        else:
            full_title = f"{brand} {model} - {year} - {price}"

        results.append((full_title, link))

    return results

app = Client("sslv_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.text & ~filters.command("start"))
def numeric_input_handler(client: Client, message: Message):
    user_id = message.from_user.id
    state = user_states.get(user_id, {})
    field = state.pop("awaiting_numeric_input", None)
    if field:
        value = message.text.strip()
        if value.isdigit():
            user_states[user_id]["filters"][field] = value
            message.reply_text(f"{filter_labels.get(field, field)} set to {value}")
        else:
            message.reply_text("Please enter a valid number.")

@app.on_message(filters.command("start"))
def start_handler(client: Client, message: Message):
    message.reply_text("Select a car brand:", reply_markup=get_brand_keyboard(page=1))

@app.on_callback_query()
def cb_handler(client: Client, query: CallbackQuery):
    data = query.data
    user_id = query.from_user.id
    parts = data.split(":", 2)

    if parts[0] == "nav":
        _, action, p = parts
        page = int(p)
        query.edit_message_reply_markup(get_brand_keyboard(page))
        return

    if parts[0] == "brand":
        sel = parts[1]
        if sel == "all":
            href = "all"
        else:
            i = int(sel)
            href = brand_links[i][1]
        user_states[user_id] = {
            "brand_href": href,
            "sort": None,
            "filter_options": {},
            "filters": {}
        }
        query.edit_message_text("Choose sorting:", reply_markup=get_sort_keyboard())
        return

    if parts[0] == "sort":
        key = parts[1]
        if key == "skip":
            user_states[user_id]["sort"] = "date_desc"
        else:
            user_states[user_id]["sort"] = key
        state = user_states[user_id]
        state["filter_options"] = parse_filter_options(state["brand_href"])
        query.edit_message_text("Select additional filters:", reply_markup=get_filter_keyboard(user_id))
        return

    if parts[0] == "filter_sel":
        field = parts[1]
        query.edit_message_reply_markup(get_filter_values_keyboard(field, user_id))
        return

    if parts[0] == "filter_val":
        _, field, val = parts
        user_states[user_id]["filters"][field] = val
        query.answer(f"{labelize(field)} set")
        query.edit_message_reply_markup(get_filter_keyboard(user_id))
        return

    elif parts[0] == "numeric_input":
        field = parts[1]
        user_states[user_id]["awaiting_numeric_input"] = field
        query.message.reply_text(f"Enter value for {filter_labels.get(field, field)}:")
        return

    if data == "filter_back":
        query.edit_message_reply_markup(get_filter_keyboard(user_id))
        return

    if data == "apply":
        query.edit_message_reply_markup(
            InlineKeyboardMarkup([[InlineKeyboardButton("Show Results", callback_data="show")]])
        )
        return

    if data == "reset":
        user_states[user_id]["filters"].clear()
        query.answer("Filters reset")
        return

    if data == "show":
        results = fetch_results(user_states[user_id])
        if results:
            rows = [[InlineKeyboardButton(f"{i+1}. {t}", url=l)] for i, (t, l) in enumerate(results)]
            text = "Here are the latest ads:\n\n" + format_user_selection(user_id)
            query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))
        else:
            query.edit_message_text("No results found with current filters.")
        return

    query.answer()

if __name__ == "__main__":
    brand_links = fetch_brands()
    app.run()
