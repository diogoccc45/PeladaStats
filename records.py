from flask import Blueprint, render_template
from flask_login import login_required

import stats as stats_mod
from database import get_db

bp = Blueprint("records", __name__, url_prefix="/recordes")


@bp.route("/")
@login_required
def lista():
    db = get_db()
    records = stats_mod.get_records(db)
    return render_template("records.html", records=records)
