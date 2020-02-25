import time

start = time.time()

time.sleep(30)

stop = time.time()

time_final = round((stop - start)/60, 2)
print(f"The final time was {time_final} minutes.")
