"""Filtering helpers ported from SSG AGT (app.py) -- kept in step with the supervisor's
V1.84 logic: multi-term account search (comma / semicolon / pipe / newline), W. HRS filter,
R. BAL sorting, and the Permanent Stop mixed view."""
import re
import pandas as pd

MONITOR_SLUGS={'agent':'Agent Accounts','personal':'Personal Accounts','vip':'VIP Accounts','withdrawal':'Withdrawal Only','permanent-stop':'Permanent Stop Accounts'}
MONITOR_PERMS={'Agent Accounts':'monitoring_agent','Personal Accounts':'monitoring_personal','VIP Accounts':'monitoring_vip','Withdrawal Only':'monitoring_withdrawal','Permanent Stop Accounts':'monitoring_permanent_stop'}
OVERVIEW_SLUGS={'agent':'Agent Accounts','personal':'Personal Accounts','high-discrepancy':'High Discrepancy','limit-reached':'Limit Reached'}
OVERVIEW_PERMS={'Agent Accounts':'overview_agent','Personal Accounts':'overview_personal','High Discrepancy':'overview_high_discrepancy','Limit Reached':'overview_limit_reached'}

def parse_amount_input(value, default=None):
    """Parse numeric filter input, accepting commas and K/M/B suffixes."""
    text=str(value or '').strip().replace(',', '').replace(' ', '')
    if not text: return default
    m=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+))(k|m|b)?', text, flags=re.I)
    if not m: return default
    number=float(m.group(1)); suffix=(m.group(2) or '').lower()
    mult={'':1,'k':1_000,'m':1_000_000,'b':1_000_000_000}[suffix]
    return number*mult


def _search_terms(value):
    # Allow multiple account searches separated by comma, semicolon, pipe, or newline.
    import re
    if value is None:
        return []
    raw=str(value).strip()
    if not raw:
        return []
    return [t.strip() for t in re.split(r'[,;|\n\r]+', raw) if t.strip()]

def _contains_any_terms(series, value):
    terms=_search_terms(value)
    if not terms:
        return pd.Series(True,index=series.index)
    text=series.astype(str)
    mask=pd.Series(False,index=series.index)
    for term in terms:
        mask = mask | text.str.contains(term,case=False,na=False,regex=False)
    return mask

def filter_monitoring_dataframe(df, slug, q='', status=None, code=None, wallet=None, limit_status=None, whrs=None, sort_rbal=''):
    status,status_code = status or [], limit_status or []
    code = code or []
    wallet = wallet or []
    whrs = whrs or []
    part=df.copy() if df is not None else pd.DataFrame()
    typ=MONITOR_SLUGS.get(slug)
    if slug == 'permanent-stop':
        if '_PERMANENT_STOP' in part.columns: part=part[part['_PERMANENT_STOP'].eq(True)].copy()
    elif typ and '_TYPE' in part.columns: part=part[part['_TYPE'].eq(typ)].copy()
    for field,values in [('STATUS',status),('CODE',code),('WALLET',wallet),('LIMIT STATUS',status_code),('W. HRS',whrs)]:
        if values and field in part.columns:
            allowed={str(v).strip().casefold() for v in values if str(v).strip()}
            if allowed: part=part[part[field].astype(str).str.strip().str.casefold().isin(allowed)].copy()
    if q and not part.empty and 'ACCOUNTS' in part.columns:
        part=part[_contains_any_terms(part['ACCOUNTS'],q)].copy()
    if not part.empty and sort_rbal in ('asc','desc') and 'R. BAL' in part.columns:
        part=part.assign(_SORT_RBAL=pd.to_numeric(part['R. BAL'],errors='coerce').fillna(float('-inf'))).sort_values('_SORT_RBAL',ascending=(sort_rbal=='asc'),kind='stable').drop(columns=['_SORT_RBAL'])
    elif not part.empty and 'ACCOUNTS' in part.columns:
        part=part.assign(_SORT_ACCOUNT=part['ACCOUNTS'].astype(str).str.strip().str.upper()).sort_values('_SORT_ACCOUNT',kind='stable').drop(columns=['_SORT_ACCOUNT'])
    return part

def filter_overview_dataframe(df, slug, threshold='', code='', acct_type='', wallet='', category='ALL', q='', limit_type='ALL', status=None, status_code=None, sort_rbal=''):
    status,status_code = status or [], status_code or []
    typ=OVERVIEW_SLUGS.get(slug)
    part=df.copy() if df is not None else pd.DataFrame()
    if typ=='Limit Reached':
        if '_TYPE' in part.columns: part=part[part['_TYPE'].eq('Personal Accounts')].copy()
        if 'LIMIT STATUS' in part.columns:
            n=part['LIMIT STATUS'].astype(str).str.strip().str.casefold(); lt=str(limit_type or 'ALL').casefold()
            if lt=='daily': part=part[n.eq('daily reach limit')].copy()
            elif lt=='monthly': part=part[n.eq('monthly reach limit')].copy()
            else: part=part[n.isin(['daily reach limit','monthly reach limit'])].copy()
        if q and not part.empty and 'ACCOUNTS' in part.columns: part=part[_contains_any_terms(part['ACCOUNTS'],q)].copy()
        if not part.empty and sort_rbal in ('asc','desc') and 'R. BAL' in part.columns:
            part=part.assign(_SORT_RBAL=pd.to_numeric(part['R. BAL'],errors='coerce').fillna(float('-inf'))).sort_values('_SORT_RBAL',ascending=(sort_rbal=='asc'),kind='stable').drop(columns=['_SORT_RBAL'])
        elif not part.empty and 'ACCOUNTS' in part.columns: part=part.assign(_SORT_ACCOUNT=part['ACCOUNTS'].astype(str).str.strip().str.upper()).sort_values('_SORT_ACCOUNT',kind='stable').drop(columns=['_SORT_ACCOUNT'])
        return part
    if typ=='High Discrepancy':
        cat=str(category or 'ALL').casefold()
        if cat=='agent' and '_TYPE' in part.columns: part=part[part['_TYPE'].eq('Agent Accounts')].copy()
        elif cat=='personal' and '_TYPE' in part.columns: part=part[part['_TYPE'].eq('Personal Accounts')].copy()
        raw=parse_amount_input(threshold,None)
        if raw is None: return part.iloc[0:0].copy()
        discrepancy=pd.to_numeric(part.get('DISCREP'),errors='coerce').fillna(0)
        part=part.loc[discrepancy>=raw].copy()
        for field,values in [('STATUS',status),('CODE',status_code)]:
            if values and field in part.columns:
                allowed={str(v).strip().casefold() for v in values if str(v).strip()}
                if allowed: part=part[part[field].astype(str).str.strip().str.casefold().isin(allowed)].copy()
        if q and not part.empty and 'ACCOUNTS' in part.columns: part=part[_contains_any_terms(part['ACCOUNTS'],q)].copy()
        if not part.empty and sort_rbal in ('asc','desc') and 'R. BAL' in part.columns:
            part=part.assign(_SORT_RBAL=pd.to_numeric(part['R. BAL'],errors='coerce').fillna(float('-inf'))).sort_values('_SORT_RBAL',ascending=(sort_rbal=='asc'),kind='stable').drop(columns=['_SORT_RBAL'])
        elif not part.empty and 'DISCREP' in part.columns: part=part.assign(_SORT_DISCREP=pd.to_numeric(part['DISCREP'],errors='coerce').fillna(float('-inf'))).sort_values(['_SORT_DISCREP','ACCOUNTS'],ascending=[False,True],kind='stable').drop(columns=['_SORT_DISCREP'])
        return part
    if '_TYPE' in part.columns: part=part[part['_TYPE'].eq(typ)].copy()
    raw=parse_amount_input(threshold,None)
    if raw is None: return part.iloc[0:0].copy()
    mrc=pd.to_numeric(part.get('MRC LMT'),errors='coerce').fillna(0); dep=pd.to_numeric(part.get('DEPOSIT'),errors='coerce').fillna(0)
    part=part[(mrc-dep)<=raw].copy()
    for field,val in [('CODE',code),('ACCT TYPE',acct_type),('WALLET',wallet)]:
        if val and field in part.columns: part=part[part[field].astype(str).str.strip().eq(val)]
    if q and not part.empty and 'ACCOUNTS' in part.columns: part=part[_contains_any_terms(part['ACCOUNTS'],q)].copy()
    if not part.empty and sort_rbal in ('asc','desc') and 'R. BAL' in part.columns:
        part=part.assign(_SORT_RBAL=pd.to_numeric(part['R. BAL'],errors='coerce').fillna(float('-inf'))).sort_values('_SORT_RBAL',ascending=(sort_rbal=='asc'),kind='stable').drop(columns=['_SORT_RBAL'])
    elif not part.empty and 'ACCOUNTS' in part.columns: part=part.assign(_SORT_ACCOUNT=part['ACCOUNTS'].astype(str).str.strip().str.upper()).sort_values('_SORT_ACCOUNT',kind='stable').drop(columns=['_SORT_ACCOUNT'])
    return part

def summary_table_with_row_total(df):
    if df is None or df.empty: return df
    out=df.copy(); nums=[]
    for c in out.columns[1:]:
        vals=pd.to_numeric(out[c].astype(str).str.replace(',','',regex=False),errors='coerce')
        if vals.notna().any(): nums.append(c)
    total=pd.Series(0.0,index=out.index)
    for c in nums: total += pd.to_numeric(out[c].astype(str).str.replace(',','',regex=False),errors='coerce').fillna(0)
    out['TOTAL']=total
    return out
