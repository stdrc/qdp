# QDP (QQ-based Datagram Protocol)

QDP is a transport protocol based on QQ messages. It can transfer any binary data through QQ messages, and do the fragmentation and reassembly things automatically.

Currently, QDP is just a proof of concept. The transfer rate is very very low, which according to limited tests, is around 20~30 Kbps (at 5 msg/s).

In QDP, QQ number is used as something like IP address. The concept "packet" is similar to the one in UDP, and "fragment" is similar to IP fragment.

This repo contains a rough implementation of QDP in Python, using "[酷Q](https://cqp.cc)" and "[CQHTTP](https://cqhttp.cc)" as its underlying QQ bot framework. You can check the [demo](demo) to see how the interfaces are.

To run the demos in this repo, you need to config CQHTTP as following:

```ini
use_ws = true
post_message_format = string
enable_rate_limited_actions = true
rate_limit_interval = 200
```
