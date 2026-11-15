set pagination off
set confirm off
set remotetimeout 15
monitor reset halt
load
python
result = gdb.execute("compare-sections", to_string=True)
print(result)
if "MIS-MATCHED" in result or "warning:" in result.lower():
    raise gdb.GdbError("Flash read-back verification failed")
end
monitor reset run
detach
quit
