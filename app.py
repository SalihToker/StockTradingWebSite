import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    username = db.execute("SELECT username FROM users WHERE id = ?",
                          session["user_id"])[0]["username"]
    purchases = db.execute(
        "SELECT symbol, SUM(shares) AS total_shares FROM purchases WHERE username = ? GROUP BY symbol", username)
    cash = db.execute("SELECT cash FROM users WHERE username = ?", username)[0]["cash"]

    portfolio = []
    for purchase in purchases:
        stock = lookup(purchase["symbol"])
        if stock:
            total_value = stock["price"] * purchase["total_shares"]
            portfolio.append({
                "symbol": purchase["symbol"],
                "name": stock["name"],
                "shares": purchase["total_shares"],
                "price": "{:.2f}".format(stock["price"]),
                "total": "{:.2f}".format(total_value)
            })

    return render_template("index.html", portfolio=portfolio, cash=cash)


@app.route("/addcash", methods=["GET", "POST"])
@login_required
def addcash():
    username = db.execute("SELECT username FROM users WHERE id = ?",
                          session["user_id"])[0]["username"]
    cash = db.execute("SELECT cash FROM users WHERE username = ?", username)[0]["cash"]

    if request.method == "POST":
        add_cash = int(request.form.get("addcash"))

        db.execute("UPDATE users SET cash = cash + ? WHERE username = ?", add_cash, username)

        cash = db.execute("SELECT cash FROM users WHERE username = ?", username)[0]["cash"]

        return render_template("addcash.html", cash=cash)

    else:
        return render_template("addcash.html", cash=cash)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        stock = lookup(symbol)
        username = db.execute("SELECT username FROM users WHERE id = ?",
                              session["user_id"])[0]["username"]
        cash = db.execute("SELECT cash FROM users WHERE username = ?", username)[0]["cash"]
        if not stock:
            return apology("invalid symbol")
        try:
            shares = int(shares)
            if shares <= 0:
                return apology("Shares must be a positive number")
        except ValueError:
            return apology("Shares must be integer")

        price = shares * stock["price"]

        if cash < price:
            return apology("can't afford")

        cash -= price
        db.execute("UPDATE users SET cash = ? WHERE username = ?", cash, username)

        db.execute("INSERT INTO purchases (username, symbol, shares, price, timestamp) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                   username, symbol, shares, "{:.2f}".format(price))

        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    username = db.execute("SELECT username FROM users WHERE id = ?",
                          session["user_id"])[0]["username"]
    purchases = db.execute(
        "SELECT * FROM purchases WHERE username = ? ORDER BY timestamp DESC", username)

    return render_template("history.html", purchases=purchases)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        stock = lookup(symbol)
        if stock:
            return render_template("quoted.html", symbol=stock["symbol"], price="{:.2f}".format(stock["price"]))

        else:
            return apology("invalid symbol")
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must provide username", 400)
        # Ensure password was submitted

        if not request.form.get("password") or request.form.get("password") != request.form.get("confirmation"):
            return apology("must provide password with same confirmation", 400)

        hash = generate_password_hash(request.form.get("password"))

        try:
            db.execute("INSERT INTO users (username, hash) VALUES (?, ?) ",
                       request.form.get("username"), hash)
        except:
            return apology("username already exist")

        return redirect("/login")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        stock = lookup(symbol)
        username = db.execute("SELECT username FROM users WHERE id = ?",
                              session["user_id"])[0]["username"]
        shares_to_sell = int(request.form.get("shares"))
        if not symbol:
            return apology("must select a stock", 400)

        # Check if the user owns shares of the selected stock
        shares = db.execute(
            "SELECT SUM(shares) AS total_shares FROM purchases WHERE username = ? AND symbol = ?", username, symbol)
        if not shares or shares[0]["total_shares"] <= 0:
            return apology("you do not own any shares of that stock", 400)

        if shares[0]["total_shares"] < shares_to_sell:
            return apology("you do not own that much shares of that stock", 400)

        if shares_to_sell <= 0 or not isinstance(shares_to_sell, int):
            return apology("shares should be more than 0 and integer")

        db.execute("INSERT INTO purchases (username, symbol, shares, price, timestamp) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                   username, symbol, -shares_to_sell, stock["price"])

        new_money = stock["price"] * shares_to_sell
        db.execute("UPDATE users SET cash = cash + ? WHERE username = ?", new_money, username)

        return redirect("/")

    else:
        username = db.execute("SELECT username FROM users WHERE id = ?",
                              session["user_id"])[0]["username"]
        purchases = db.execute(
            "SELECT symbol, SUM(shares) AS total_shares FROM purchases WHERE username = ? GROUP BY symbol", username)

        symbols = [purchase["symbol"] for purchase in purchases]
        return render_template("sell.html", symbols=symbols)
