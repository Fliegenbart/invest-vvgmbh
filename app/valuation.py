from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from .models import ValuationInput

def valuation(value:ValuationInput,at=None):
    at=at or datetime.now(timezone.utc)
    observed=value.as_of
    if observed.tzinfo is None: raise ValueError('Kurszeitpunkt muss eine Zeitzone enthalten.')
    seconds=(at-observed).total_seconds()
    if seconds < -300: raise ValueError('Kurszeitpunkt liegt in der Zukunft.')
    def f(x):return str(x.quantize(Decimal('0.01'),rounding=ROUND_HALF_UP))
    pe=f(value.price/value.eps) if value.eps is not None and value.eps>0 else None
    dy=f(value.dividend_per_share/value.price*100) if value.dividend_per_share is not None else None
    return {'pe':pe,'gross_dividend_yield_pct':dy,'stale':seconds>72*3600,
            'input':value.model_dump(mode='json'),
            'notice':'Manuelle Eingaben; keine Kursvalidierung. KGV nur bei positivem EPS. Dividendenrendite brutto, vergangene Jahresdividende nicht als Prognose. Währung, Zeitraum und Aktiengattung müssen übereinstimmen.'}
