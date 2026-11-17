# Command output

Some command output here goes through delegation-core's output filters to
save tokens: noise is dropped, errors and summaries stay. Treat a filtered
result as the complete result. When lines were cut, the output says so and
ends with a recall hint (`recall <hash>` or `Retrieve more: hash=<hash>`);
get the original with the `recall_output` tool or `delegation-core recall
<hash>`. To filter a command yourself, run it as `delegation-core shell
"<command>"`. Run it plainly only when the filtered result is unusable.
