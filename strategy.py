# 导入聚宽函数库
from jqdata import *

def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_order_cost(OrderCost(close_tax=0.001, open_commission=0.0003, min_commission=5), type='stock')
    
    g.stock_count = 10        # 持仓数量
    g.stop_loss_rate = -0.08  # 8% 硬止损线
    
    run_daily(before_market_open, time='before_open')
    run_daily(market_open, time='open')

def before_market_open(context):
    # 1. 【新增】每天重置“黑名单”
    g.sold_today = []
    
    # --- 选股逻辑 (保持不变) ---
    q = query(valuation.code, indicator.roe).filter(indicator.roe > 0)
    df = get_fundamentals(q)
    df = df.dropna()
    df = df[df['roe'] > df['roe'].median()]
    
    pool = list(df['code'])
    h = history(21, unit='1d', field='close', security_list=pool)
    
    if len(h) > 0:
        momentum = (h.iloc[-1] / h.iloc[0]) - 1
        g.my_pool = list(momentum.sort_values(ascending=False).head(g.stock_count).index)
    else:
        g.my_pool = []

def market_open(context):
    # --- 风险检测 (减震器) ---
    index_data = get_bars('000300.XSHG', count=20, unit='1d', fields=['close'])
    index_return = (index_data['close'][-1] / index_data['close'][0]) - 1
    exposure = 0.3 if index_return < -0.05 else 1.0
    
    # --- 持仓检查 ---
    for stock in list(context.portfolio.positions.keys()):
        cost = context.portfolio.positions[stock].avg_cost
        price = context.portfolio.positions[stock].price
        ret = price / cost - 1
        
        # 获取均线
        h = attribute_history(stock, 21, '1d', ['close'])
        if len(h) == 21:
            ma5 = h['close'][-5:].mean()
            ma20 = h['close'].mean()
            
            # 逻辑 1: 硬止损
            if ret <= g.stop_loss_rate:
                log.info(f"🛑 硬止损卖出: {stock}")
                order_target(stock, 0)
                g.sold_today.append(stock) # 【新增】加入黑名单
            
            # 逻辑 2: 趋势死叉
            elif ma5 < ma20:
                log.info(f"📉 趋势死叉卖出: {stock}")
                order_target(stock, 0)
                g.sold_today.append(stock) # 【新增】加入黑名单

    # --- 买入执行 ---
    cash = context.portfolio.available_cash
    target_value = context.portfolio.total_value * (exposure / g.stock_count)
    
    for security in g.my_pool:
        # 【新增】检查黑名单：如果今天刚卖过，就别买了
        if security not in g.sold_today:
            
            h = attribute_history(security, 20, '1d', ['close'])
            if len(h) == 20:
                ma5 = h['close'][-5:].mean()
                ma20 = h['close'].mean()
                
                if ma5 > ma20 and cash >= target_value:
                    if security not in context.portfolio.positions:
                        order_target_value(security, target_value)
                        cash -= target_value