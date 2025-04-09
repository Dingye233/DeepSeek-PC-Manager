import yfinance as yf
import matplotlib.pyplot as plt
import pandas as pd

# Fetch NVIDIA stock data for the last 5 years
data = yf.download('NVDA', period='5y')

# Save data to CSV
data.to_csv('workspace/nvidia_stock_data.csv')

# Plot closing price
plt.figure(figsize=(10, 6))
plt.plot(data['Close'], label='Closing Price')
plt.title('NVIDIA Stock Price (Last 5 Years)')
plt.xlabel('Date')
plt.ylabel('Price (USD)')
plt.legend()
plt.grid()
plt.savefig('workspace/nvidia_stock_price.png')
plt.show()

# Generate a simple analysis report
report = f"""NVIDIA Stock Analysis Report (Last 5 Years)
--------------------------------------------
- Highest Price: ${data['Close'].max():.2f}
- Lowest Price: ${data['Close'].min():.2f}
- Average Price: ${data['Close'].mean():.2f}
- Current Price: ${data['Close'].iloc[-1]:.2f}
"""

with open('workspace/nvidia_stock_report.txt', 'w') as f:
    f.write(report)