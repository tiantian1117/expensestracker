from __future__ import annotations

import calendar
import sqlite3
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from database import (
    add_account,
    add_transaction,
    delete_transaction,
    fetch_account_type_balances,
    fetch_accounts,
    fetch_categories,
    fetch_expense_by_category,
    fetch_monthly_summary,
    fetch_summary,
    fetch_transactions,
    initialize_database,
    update_account,
)

APP_TITLE = "My Expense Tracker"
CURRENCY = "₱"

ACCOUNT_TYPES = [
    "Paper Bills",
    "Coins",
    "E-Money",
    "Bank Deposit",
    "Other",
]

EXPENSE_CATEGORIES = [
    "Food",
    "Transportation",
    "Bills & Utilities",
    "Housing",
    "Shopping",
    "Health",
    "Education",
    "Family",
    "Entertainment",
    "Savings",
    "Debt Payment",
    "Other",
]

INCOME_CATEGORIES = [
    "Salary",
    "Allowance",
    "Business",
    "Freelance",
    "Gift",
    "Interest",
    "Refund",
    "Other",
]


def money(value: float) -> str:
    return f"{CURRENCY}{value:,.2f}"


def month_bounds(day: date) -> tuple[date, date]:
    last_day = calendar.monthrange(day.year, day.month)[1]
    return date(day.year, day.month, 1), date(day.year, day.month, last_day)


def show_success(message: str) -> None:
    st.session_state["flash_message"] = message
    st.rerun()


def display_flash_message() -> None:
    message = st.session_state.pop("flash_message", None)
    if message:
        st.success(message)


def apply_styles() -> None:
    st.markdown(
        """
        <style>
            .block-container {
                max-width: 1180px;
                padding-top: 1.7rem;
                padding-bottom: 3rem;
            }
            [data-testid="stSidebar"] {
                border-right: 1px solid rgba(128, 128, 128, 0.18);
            }
            [data-testid="stMetric"] {
                background: rgba(128, 128, 128, 0.07);
                border: 1px solid rgba(128, 128, 128, 0.16);
                border-radius: 16px;
                padding: 14px 16px;
            }
            .account-card {
                border: 1px solid rgba(128, 128, 128, 0.18);
                border-radius: 16px;
                padding: 16px;
                margin-bottom: 10px;
                background: rgba(128, 128, 128, 0.05);
            }
            .account-name {
                font-size: 0.92rem;
                opacity: 0.75;
                margin-bottom: 4px;
            }
            .account-balance {
                font-size: 1.45rem;
                font-weight: 700;
            }
            .account-type {
                font-size: 0.78rem;
                opacity: 0.62;
                margin-top: 4px;
            }
            .small-note {
                opacity: 0.70;
                font-size: 0.86rem;
            }
            div.stButton > button,
            div.stDownloadButton > button {
                border-radius: 10px;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def account_lookup(accounts: list[dict]) -> tuple[dict[str, int], dict[int, dict]]:
    label_to_id = {
        f"{account['name']} — {account['account_type']}": account["id"]
        for account in accounts
    }
    id_to_account = {account["id"]: account for account in accounts}
    return label_to_id, id_to_account


def dashboard_page() -> None:
    st.header("Dashboard")
    today = date.today()
    start_of_month, end_of_month = month_bounds(today)

    accounts = fetch_accounts(active_only=False)
    account_type_balances = fetch_account_type_balances()
    month_summary = fetch_summary(start_of_month, end_of_month)

    total_balance = sum(float(account["balance"]) for account in accounts)

    metric_columns = st.columns(4)
    metric_columns[0].metric("Total Balance", money(total_balance))
    metric_columns[1].metric("Income This Month", money(month_summary["income"]))
    metric_columns[2].metric("Expenses This Month", money(month_summary["expense"]))
    metric_columns[3].metric("Net This Month", money(month_summary["net"]))

    st.subheader("Balance by Account Type")
    if account_type_balances:
        type_columns = st.columns(min(4, len(account_type_balances)))
        for index, item in enumerate(account_type_balances):
            with type_columns[index % len(type_columns)]:
                st.markdown(
                    f"""
                    <div class="account-card">
                        <div class="account-name">{item['account_type']}</div>
                        <div class="account-balance">{money(float(item['balance']))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.subheader("Individual Accounts")
    if accounts:
        account_columns = st.columns(3)
        for index, account in enumerate(accounts):
            status = "" if account["is_active"] else " · Inactive"
            with account_columns[index % 3]:
                st.markdown(
                    f"""
                    <div class="account-card">
                        <div class="account-name">{account['name']}</div>
                        <div class="account-balance">{money(float(account['balance']))}</div>
                        <div class="account-type">{account['account_type']}{status}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
    else:
        st.info("No accounts have been created yet.")

    left, right = st.columns([1.6, 1])

    with left:
        st.subheader("Recent Activity")
        recent = fetch_transactions(limit=8)
        if recent:
            recent_df = pd.DataFrame(recent)
            recent_df["Date"] = pd.to_datetime(
                recent_df["transaction_date"]
            ).dt.strftime("%b %d, %Y")
            recent_df["Details"] = recent_df.apply(
                lambda row: (
                    f"{row['account']} → {row['destination_account']}"
                    if row["transaction_type"] == "Transfer"
                    else row["account"]
                ),
                axis=1,
            )
            recent_df["Amount"] = recent_df.apply(
                lambda row: (
                    f"-{money(row['amount'])}"
                    if row["transaction_type"] == "Expense"
                    else money(row["amount"])
                ),
                axis=1,
            )
            st.dataframe(
                recent_df[
                    ["Date", "transaction_type", "category", "Details", "Amount"]
                ].rename(
                    columns={
                        "transaction_type": "Type",
                        "category": "Category",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Add your first income or expense to see activity here.")

    with right:
        st.subheader("This Month's Spending")
        category_data = fetch_expense_by_category(start_of_month, end_of_month)
        if category_data:
            category_df = pd.DataFrame(category_data).set_index("category")
            st.bar_chart(category_df["amount"], horizontal=True)
        else:
            st.info("No expenses recorded this month.")


def transaction_page() -> None:
    st.header("Add Transaction")
    accounts = fetch_accounts(active_only=True)

    if not accounts:
        st.warning("Create or activate an account before adding transactions.")
        return

    label_to_id, id_to_account = account_lookup(accounts)
    account_labels = list(label_to_id.keys())

    transaction_type = st.segmented_control(
        "Transaction type",
        ["Expense", "Income", "Transfer"],
        default="Expense",
        selection_mode="single",
    )

    if not transaction_type:
        return

    with st.form("transaction_form", clear_on_submit=True):
        first, second = st.columns(2)
        transaction_date = first.date_input(
            "Date",
            value=date.today(),
            max_value=date.today() + timedelta(days=365),
        )
        amount = second.number_input(
            f"Amount ({CURRENCY})",
            min_value=0.0,
            step=10.0,
            format="%.2f",
        )

        source_label = st.selectbox(
            "Account" if transaction_type != "Transfer" else "From account",
            account_labels,
        )
        source_id = label_to_id[source_label]

        destination_id = None
        category = "Account Transfer"

        if transaction_type == "Transfer":
            destination_labels = [
                label for label in account_labels
                if label_to_id[label] != source_id
            ]
            if destination_labels:
                destination_label = st.selectbox(
                    "To account",
                    destination_labels,
                )
                destination_id = label_to_id[destination_label]
            else:
                st.warning("At least two active accounts are required for a transfer.")
        else:
            default_categories = (
                EXPENSE_CATEGORIES
                if transaction_type == "Expense"
                else INCOME_CATEGORIES
            )
            category_option = st.selectbox(
                "Category",
                default_categories + ["Add custom category…"],
            )
            if category_option == "Add custom category…":
                category = st.text_input("Custom category").strip()
            else:
                category = category_option

        note = st.text_area(
            "Note (optional)",
            placeholder="Example: Lunch, electricity bill, salary payment",
            height=90,
        )

        current_balance = float(id_to_account[source_id]["balance"])
        if transaction_type in {"Expense", "Transfer"}:
            st.caption(f"Available balance: {money(current_balance)}")

        submitted = st.form_submit_button(
            "Save Transaction",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        if amount <= 0:
            st.error("Enter an amount greater than zero.")
            return
        if not category:
            st.error("Enter a category.")
            return
        if transaction_type == "Transfer" and destination_id is None:
            st.error("Select a destination account.")
            return
        if transaction_type in {"Expense", "Transfer"} and amount > current_balance:
            st.error(
                f"This transaction is higher than the available balance "
                f"of {money(current_balance)}."
            )
            return

        try:
            add_transaction(
                transaction_date=transaction_date,
                transaction_type=transaction_type,
                category=category,
                amount=amount,
                account_id=source_id,
                destination_account_id=destination_id,
                note=note,
            )
            show_success(f"{transaction_type} saved successfully.")
        except (ValueError, sqlite3.IntegrityError) as error:
            st.error(str(error))


def accounts_page() -> None:
    st.header("Accounts")
    st.caption(
        "Keep cash, coins, e-money, and bank deposits separate. "
        "Opening balances should represent the amount available before "
        "you begin recording transactions."
    )

    with st.expander("Add a New Account", expanded=False):
        with st.form("add_account_form", clear_on_submit=True):
            name = st.text_input(
                "Account name",
                placeholder="Example: BPI Savings or GCash",
            )
            account_type = st.selectbox("Account type", ACCOUNT_TYPES)
            opening_balance = st.number_input(
                f"Opening balance ({CURRENCY})",
                min_value=0.0,
                step=100.0,
                format="%.2f",
            )
            submitted = st.form_submit_button(
                "Add Account",
                type="primary",
                use_container_width=True,
            )

        if submitted:
            try:
                add_account(name, account_type, opening_balance)
                show_success("Account added successfully.")
            except sqlite3.IntegrityError:
                st.error("An account with that name already exists.")
            except ValueError as error:
                st.error(str(error))

    accounts = fetch_accounts(active_only=False)
    if not accounts:
        st.info("No accounts found.")
        return

    st.subheader("Manage Existing Accounts")
    account_names = {
        f"{account['name']} — {money(float(account['balance']))}": account
        for account in accounts
    }
    selected_label = st.selectbox("Choose an account", list(account_names.keys()))
    selected = account_names[selected_label]

    with st.form("edit_account_form"):
        edit_name = st.text_input("Account name", value=selected["name"])
        type_index = (
            ACCOUNT_TYPES.index(selected["account_type"])
            if selected["account_type"] in ACCOUNT_TYPES
            else ACCOUNT_TYPES.index("Other")
        )
        edit_type = st.selectbox(
            "Account type",
            ACCOUNT_TYPES,
            index=type_index,
        )
        edit_opening = st.number_input(
            f"Opening balance ({CURRENCY})",
            min_value=0.0,
            value=float(selected["opening_balance"]),
            step=100.0,
            format="%.2f",
            help=(
                "Changing the opening balance changes the calculated "
                "current balance. Existing transactions are not changed."
            ),
        )
        edit_active = st.checkbox(
            "Active account",
            value=bool(selected["is_active"]),
            help="Inactive accounts remain in reports but cannot receive new entries.",
        )
        saved = st.form_submit_button(
            "Save Account Changes",
            type="primary",
            use_container_width=True,
        )

    if saved:
        try:
            update_account(
                selected["id"],
                edit_name,
                edit_type,
                edit_opening,
                edit_active,
            )
            show_success("Account updated successfully.")
        except sqlite3.IntegrityError:
            st.error("An account with that name already exists.")
        except ValueError as error:
            st.error(str(error))


def history_page() -> None:
    st.header("Transaction History")
    accounts = fetch_accounts(active_only=False)
    categories = fetch_categories()

    default_start = date.today() - timedelta(days=30)
    default_end = date.today()

    with st.expander("Filters", expanded=True):
        col1, col2, col3 = st.columns(3)
        start_date = col1.date_input("From", value=default_start)
        end_date = col2.date_input("To", value=default_end)
        transaction_type = col3.selectbox(
            "Type",
            ["All", "Expense", "Income", "Transfer"],
        )

        col4, col5 = st.columns(2)
        account_options = {"All accounts": None}
        account_options.update(
            {
                f"{account['name']} — {account['account_type']}": account["id"]
                for account in accounts
            }
        )
        account_label = col4.selectbox("Account", list(account_options.keys()))
        category = col5.selectbox("Category", ["All"] + categories)

    if start_date > end_date:
        st.error("The start date must be before or equal to the end date.")
        return

    records = fetch_transactions(
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        account_id=account_options[account_label],
        category=category,
    )

    if not records:
        st.info("No transactions match these filters.")
        return

    dataframe = pd.DataFrame(records)
    dataframe["Date"] = pd.to_datetime(
        dataframe["transaction_date"]
    ).dt.strftime("%b %d, %Y")
    dataframe["Account"] = dataframe.apply(
        lambda row: (
            f"{row['account']} → {row['destination_account']}"
            if row["transaction_type"] == "Transfer"
            else row["account"]
        ),
        axis=1,
    )
    dataframe["Amount"] = dataframe["amount"].map(money)

    display_df = dataframe[
        ["id", "Date", "transaction_type", "category", "Account", "Amount", "note"]
    ].rename(
        columns={
            "id": "ID",
            "transaction_type": "Type",
            "category": "Category",
            "note": "Note",
        }
    )

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )

    export_df = dataframe[
        [
            "transaction_date",
            "transaction_type",
            "category",
            "amount",
            "account",
            "destination_account",
            "note",
        ]
    ].rename(
        columns={
            "transaction_date": "date",
            "transaction_type": "type",
            "destination_account": "destination",
        }
    )
    csv_data = export_df.to_csv(index=False).encode("utf-8")

    download_col, delete_col = st.columns([1, 1])
    with download_col:
        st.download_button(
            "Download Filtered CSV",
            data=csv_data,
            file_name=f"expense_transactions_{datetime.now():%Y%m%d}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with delete_col:
        with st.popover("Delete a Transaction", use_container_width=True):
            transaction_id = st.selectbox(
                "Transaction ID",
                display_df["ID"].tolist(),
                format_func=lambda item: (
                    f"#{item} — "
                    f"{display_df.loc[display_df['ID'] == item, 'Date'].iloc[0]} · "
                    f"{display_df.loc[display_df['ID'] == item, 'Type'].iloc[0]} · "
                    f"{display_df.loc[display_df['ID'] == item, 'Amount'].iloc[0]}"
                ),
            )
            st.warning("Deleting a transaction cannot be undone.")
            if st.button(
                "Confirm Delete",
                type="primary",
                use_container_width=True,
            ):
                delete_transaction(int(transaction_id))
                show_success("Transaction deleted.")


def reports_page() -> None:
    st.header("Reports")
    today = date.today()
    default_start = date(today.year, 1, 1)

    filter_col1, filter_col2 = st.columns(2)
    start_date = filter_col1.date_input("Report start", value=default_start)
    end_date = filter_col2.date_input("Report end", value=today)

    if start_date > end_date:
        st.error("The report start date must be before the end date.")
        return

    summary = fetch_summary(start_date, end_date)
    summary_cols = st.columns(3)
    summary_cols[0].metric("Income", money(summary["income"]))
    summary_cols[1].metric("Expenses", money(summary["expense"]))
    summary_cols[2].metric("Net", money(summary["net"]))

    st.subheader("Income vs. Expenses by Month")
    monthly = fetch_monthly_summary(months=12)
    if monthly:
        monthly_df = pd.DataFrame(monthly)
        monthly_df["month"] = pd.to_datetime(monthly_df["month"])
        monthly_df = monthly_df.set_index("month")
        st.bar_chart(monthly_df[["income", "expense"]])
    else:
        st.info("No monthly data is available yet.")

    st.subheader("Expenses by Category")
    categories = fetch_expense_by_category(start_date, end_date)
    if categories:
        category_df = pd.DataFrame(categories)
        chart_col, table_col = st.columns([1.4, 1])
        with chart_col:
            st.bar_chart(
                category_df.set_index("category")["amount"],
                horizontal=True,
            )
        with table_col:
            category_df["Share"] = (
                category_df["amount"] / category_df["amount"].sum() * 100
            ).map(lambda value: f"{value:.1f}%")
            category_df["Amount"] = category_df["amount"].map(money)
            st.dataframe(
                category_df[["category", "Amount", "Share"]].rename(
                    columns={"category": "Category"}
                ),
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.info("No expenses were recorded for this period.")


def main() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="💰",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    initialize_database()
    apply_styles()
    display_flash_message()

    with st.sidebar:
        st.title("💰 Expense Tracker")
        st.caption("Simple personal finance tracking")
        page = st.radio(
            "Navigation",
            [
                "Dashboard",
                "Add Transaction",
                "Accounts",
                "Transaction History",
                "Reports",
            ],
            label_visibility="collapsed",
        )
        st.divider()
        st.markdown(
            """
            <div class="small-note">
                Data is saved locally in <code>data/expense_tracker.db</code>.
                Keep a backup of this file when moving the app.
            </div>
            """,
            unsafe_allow_html=True,
        )

    if page == "Dashboard":
        dashboard_page()
    elif page == "Add Transaction":
        transaction_page()
    elif page == "Accounts":
        accounts_page()
    elif page == "Transaction History":
        history_page()
    elif page == "Reports":
        reports_page()


if __name__ == "__main__":
    main()
