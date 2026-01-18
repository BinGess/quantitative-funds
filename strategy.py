from jqdata import * 
 
def initialize(context): 
    # 设定沪深300作为基准 
    set_benchmark('000300.XSHG') 
    set_option('use_real_price', True) # 真实价格模式 
    
    # 策略全局变量 
    g.stock_count = 10       # 目标持仓数 
    g.stop_loss_rate = -0.08  # 8% 硬止损线 
    
    # 手续费设定 
    set_order_cost(OrderCost(close_tax=0.001, open_commission=0.0003), type='stock') 
    
    # 定时运行函数 
    run_daily(before_market_open, time='before_open') 
    run_daily(market_open, time='open') 

## 1. 选股层（分层筛选逻辑） 
def before_market_open(context): 
    # --- 第一步：基本面政审 (Quality) --- 
    q = query(valuation.code, indicator.roe, valuation.pe_ratio) 
    df = get_fundamentals(q) 
    
    # 剔除亏损和缺失数据 
    df = df[df['roe'] > 0].dropna() 
    # 分层过滤：只留 ROE 排名在前 50% 的公司（方案 B） 
    df = df[df['roe'] > df['roe'].median()] 
    
    # --- 第二步：动能择优 (Momentum) --- 
    pool = list(df['code']) 
    # 获取过去 20 天的涨幅 
    h = history(21, unit='1d', field='close', security_list=pool) 
    momentum = (h.iloc[-1] / h.iloc[0]) - 1 
    
    # 在 ROE 合格池中，按涨幅选前 10 名 
    g.my_pool = list(momentum.sort_values(ascending=False).head(g.stock_count).index) 
    log.info(f"今日入选池: {g.my_pool}") 

## 2. 执行层（动态仓位与硬止损） 
def market_open(context): 
    # --- 风险检测 (减震器) --- 
    index_data = get_bars('000300.XSHG', count=20, unit='1d', fields=['close']) 
    index_return = (index_data['close'][-1] / index_data['close'][0]) - 1 
    # 大盘风险控制 
    exposure = 0.3 if index_return < -0.05 else 1.0 
    
    # --- 持仓检查（硬止损逻辑） --- 
    for stock in list(context.portfolio.positions.keys()): 
        cost = context.portfolio.positions[stock].avg_cost 
        price = context.portfolio.positions[stock].price 
        ret = price / cost - 1 
        
        # 只要亏损超过 8%，立刻砍掉 
        if ret <= g.stop_loss_rate: 
            log.info(f"== 达到止损线，卖出: {stock} ==") 
            order_target(stock, 0) 
            
    # --- 买入执行 --- 
    cash = context.portfolio.available_cash 
    target_value = context.portfolio.total_value * (exposure / g.stock_count) 
    
    for security in g.my_pool: 
        # 获取均线信号 
        h = attribute_history(security, 20, '1d', ['close']) 
        ma5 = h['close'][-5:].mean() 
        ma20 = h['close'].mean() 
        
        # 金叉买入且有足够现金 
        if ma5 > ma20 and cash >= target_value: 
            if security not in context.portfolio.positions: 
                log.info(f"符合动能+金叉，买入: {security}") 
                order_target_value(security, target_value) 
                cash -= target_value
