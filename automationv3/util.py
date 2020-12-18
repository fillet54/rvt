# This is based on twitters snowflake algorithm
# See: https://blog.twitter.com/engineering/en_us/a/2010/announcing-snowflake.html

# This source was adapted from:
#   https://github.com/cablehead/python-snowflake
# and has a Creative Commons Zero v1.0 Universal (CC0) license attached.
#
# This was modified to increase the worker id to be the the maximum size possible
# and remove sequence id. There should not be a instance where an id is generated
# in the same millisecond and the current solution to sleep for a millisecond is
# sufficient for our purposes.
import time
import logging

log = logging.getLogger(__name__)


# Tuesday, December 15, 2020 00:00:00.000 GMT
epoch = 1607990400000

worker_id_bits = 22
max_worker_id = -1 ^ (-1 << worker_id_bits)
timestamp_left_shift = worker_id_bits


def snowflake_to_timestamp(_id):
    _id = _id >> 22   # strip the lower 22 bits
    _id += epoch      # adjust for epoch
    _id = _id / 1000  # convert from milliseconds to seconds
    return _id


def id_generator(worker_id, sleep=lambda x: time.sleep(x / 1000.0)):
    assert worker_id >= 0 and worker_id <= max_worker_id

    last_timestamp = -1

    while True:
        timestamp = int(time.time() * 1000)

        if last_timestamp > timestamp:
            log.warning(
                f"clock is moving backwards. waiting until {last_timestamp}")
            sleep(last_timestamp - timestamp)
            continue

        if last_timestamp == timestamp:
            log.warning("ID overrun. Sleeping for 1ms.")
            sleep(1)
            continue

        last_timestamp = timestamp

        yield (((timestamp - epoch) << timestamp_left_shift) | worker_id)


# Added the following convenience function for getting a client unique id
# generator. It uses the hash of the users login name for the worker id.
import os
import hashlib
import struct


def get_client_unique_id_generator():
    username = os.getlogin()
    hash = hashlib.sha256(username.encode())
    client_id = struct.unpack('I', hash.digest()[:4])[0] & max_worker_id
    return id_generator(client_id)
