"""MySQL/MariaDB 状态库客户端（纯标准库实现，无第三方依赖）。

给 ``wxg.py`` 的 MySQL 后端使用，接口刻意保持与 sqlite3 相近：

    conn = connect("mysql://user:password@host:3306/dbname")
    cur = conn.execute("SELECT * FROM nodes WHERE repo=?", (repo_id,))
    rows = cur.fetchall()          # list[dict]
    conn.commit() / conn.rollback()
    conn.close()

实现范围：
- 握手协议 v10，CLIENT_PROTOCOL_41 / SECURE_CONNECTION / PLUGIN_AUTH /
  CONNECT_WITH_DB，不启用 CLIENT_DEPRECATE_EOF（用 EOF 包收尾）。
- 认证：mysql_native_password，含服务端发起的 AuthSwitchRequest。
- 文本协议：参数占位符 ``?`` 在客户端做字面量转义；结果集列按协议字段
  类型转成 int/float，NULL 转 None，其余按 utf-8 文本。
- 事务：连接建立后 ``SET SESSION autocommit=0``，commit/rollback 生效。

已知边界（故意不实现）：
- TLS、压缩、LOAD DATA LOCAL INFILE。
- caching_sha2_password / ed25519 等其它认证插件（会抛 MySQLDatabaseError）。
- CLIENT_MULTI_STATEMENTS（一次 execute 只能一条语句；executescript 自行拆分）。
- 存储过程/多结果集（不协商 CLIENT_MULTI_RESULTS）。
- 依赖 ``NO_BACKSLASH_ESCAPES`` sql_mode 的服务器配置（默认 sql_mode 不含该项）。
- 二进制非 utf-8 列（BLOB）按 utf-8 解码，可能抛 UnicodeDecodeError。
- 结果集里重名列会让 dict 后值覆盖前值。
"""

from __future__ import annotations

import hashlib
import socket
import struct
import urllib.parse
from typing import Any, Sequence

__all__ = [
    "MySQLDatabaseError",
    "MySQLConnection",
    "MySQLCursor",
    "connect",
    "is_integrity_error",
]

_CONNECT_TIMEOUT = 5.0
_DEFAULT_PORT = 3306
_MAX_PACKET = 0x00FFFFFF

# 客户端能力位
_CLIENT_LONG_PASSWORD = 0x00000001
_CLIENT_LONG_FLAG = 0x00000004
_CLIENT_CONNECT_WITH_DB = 0x00000008
_CLIENT_PROTOCOL_41 = 0x00000200
_CLIENT_TRANSACTIONS = 0x00002000
_CLIENT_SECURE_CONNECTION = 0x00008000
_CLIENT_PLUGIN_AUTH = 0x00080000

_CLIENT_BASE_CAPABILITIES = (
    _CLIENT_LONG_PASSWORD
    | _CLIENT_LONG_FLAG
    | _CLIENT_PROTOCOL_41
    | _CLIENT_TRANSACTIONS
    | _CLIENT_SECURE_CONNECTION
    | _CLIENT_PLUGIN_AUTH
)

_CLIENT_CHARSET_UTF8MB4 = 45  # utf8mb4_general_ci
_MYSQL_NATIVE_PASSWORD = "mysql_native_password"

# MySQL 列类型（Protocol::ColumnDefinition41 的 type 字段）
_TYPE_DECIMAL = 0
_TYPE_TINY = 1
_TYPE_SHORT = 2
_TYPE_LONG = 3
_TYPE_FLOAT = 4
_TYPE_DOUBLE = 5
_TYPE_NULL = 6
_TYPE_TIMESTAMP = 7
_TYPE_LONGLONG = 8
_TYPE_INT24 = 9
_TYPE_DATE = 10
_TYPE_TIME = 11
_TYPE_DATETIME = 12
_TYPE_YEAR = 13
_TYPE_NEWDATE = 14
_TYPE_VARCHAR = 15
_TYPE_BIT = 16
_TYPE_TIMESTAMP2 = 17
_TYPE_DATETIME2 = 18
_TYPE_TIME2 = 19
_TYPE_JSON = 245
_TYPE_NEWDECIMAL = 246
_TYPE_ENUM = 247
_TYPE_SET = 248
_TYPE_TINY_BLOB = 249
_TYPE_MEDIUM_BLOB = 250
_TYPE_LONG_BLOB = 251
_TYPE_BLOB = 252
_TYPE_VAR_STRING = 253
_TYPE_STRING = 254
_TYPE_GEOMETRY = 255

_INTEGER_TYPES = frozenset(
    {
        _TYPE_TINY,
        _TYPE_SHORT,
        _TYPE_LONG,
        _TYPE_LONGLONG,
        _TYPE_INT24,
        _TYPE_YEAR,
    }
)
_FLOAT_TYPES = frozenset({_TYPE_FLOAT, _TYPE_DOUBLE})
_DECIMAL_TYPES = frozenset({_TYPE_DECIMAL, _TYPE_NEWDECIMAL})

# 视为“完整性约束错误”的 MySQL/MariaDB errno：
# 1022 重复键、1048 非空约束、1062 重复条目、1169 唯一键冲突、
# 1216/1217 外键（旧编号）、1451/1452 外键（新编号）、1557 外键重复键、
# 3819 CHECK 约束（MySQL 8.0+/MariaDB 10.2+）。
_INTEGRITY_ERRNOS = frozenset(
    {
        1022,
        1048,
        1062,
        1169,
        1216,
        1217,
        1451,
        1452,
        1557,
        3819,
    }
)


class MySQLDatabaseError(Exception):
    """MySQL/MariaDB 错误：服务端错误带 errno/sqlstate，客户端错误 errno 为 None。"""

    errno: int | None
    sqlstate: str | None

    def __init__(
        self,
        message: str,
        errno: int | None = None,
        sqlstate: str | None = None,
    ) -> None:
        super().__init__(message)
        self.errno = errno
        self.sqlstate = sqlstate


def is_integrity_error(exc: BaseException) -> bool:
    """判断异常是否对应唯一键/非空/外键等完整性约束错误。"""
    if not isinstance(exc, MySQLDatabaseError):
        return False
    return exc.errno in _INTEGRITY_ERRNOS


def connect(url: str) -> "MySQLConnection":
    """按 ``mysql://user:password@host:port/dbname`` 建立连接。

    用户名/密码/库名都按 URL 百分号编码解码；密码可含 ``@ : / % ? #`` 等字符。
    连接与读写超时均为 5 秒。
    """
    target = _parse_url(url)
    sock: socket.socket | None = None
    try:
        sock = socket.create_connection(
            (target.host, target.port), timeout=_CONNECT_TIMEOUT
        )
        sock.settimeout(_CONNECT_TIMEOUT)
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        conn = MySQLConnection(sock, target)
        conn._startup()
        return conn
    except MySQLDatabaseError:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        raise
    except OSError as exc:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        raise MySQLDatabaseError(
            f"无法连接 MySQL 服务器 {target.host}:{target.port}: {exc}"
        ) from exc
    except BaseException:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        raise


class _Target:
    __slots__ = ("host", "port", "user", "password", "database")

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str | None,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database


def _parse_url(url: str) -> _Target:
    if not isinstance(url, str):
        raise TypeError("MySQL URL 必须是 str")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("mysql", "mariadb"):
        raise MySQLDatabaseError(
            f"不支持的 MySQL URL 协议: {parts.scheme!r}（应为 mysql://）"
        )
    if not parts.hostname:
        raise MySQLDatabaseError("MySQL URL 缺少主机名")
    try:
        port = parts.port or _DEFAULT_PORT
    except ValueError as exc:
        raise MySQLDatabaseError(f"MySQL URL 端口非法: {exc}") from exc
    user = urllib.parse.unquote(parts.username or "")
    password = urllib.parse.unquote(parts.password or "")
    database = urllib.parse.unquote(parts.path[1:]) if parts.path.startswith("/") else ""
    if not user:
        raise MySQLDatabaseError("MySQL URL 缺少用户名")
    return _Target(
        host=parts.hostname,
        port=port,
        user=user,
        password=password,
        database=database or None,
    )


class _Reader:
    """小端协议字段读取器，越界时抛协议错误。"""

    __slots__ = ("data", "pos")

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    @property
    def remaining(self) -> int:
        return len(self.data) - self.pos

    def eof(self) -> bool:
        return self.pos >= len(self.data)

    def peek_byte(self) -> int:
        if self.eof():
            raise _protocol_error("数据包意外结束")
        return self.data[self.pos]

    def take(self, size: int) -> bytes:
        if size < 0 or self.remaining < size:
            raise _protocol_error("数据包意外结束")
        chunk = self.data[self.pos : self.pos + size]
        self.pos += size
        return chunk

    def byte(self) -> int:
        return self.take(1)[0]

    def uint16(self) -> int:
        return int.from_bytes(self.take(2), "little")

    def uint24(self) -> int:
        return int.from_bytes(self.take(3), "little")

    def uint32(self) -> int:
        return int.from_bytes(self.take(4), "little")

    def uint64(self) -> int:
        return int.from_bytes(self.take(8), "little")

    def lenenc(self) -> int | None:
        first = self.byte()
        if first < 0xFB:
            return first
        if first == 0xFB:
            return None
        if first == 0xFC:
            return self.uint16()
        if first == 0xFD:
            return self.uint24()
        if first == 0xFE:
            return self.uint64()
        raise _protocol_error("非法的 length-encoded integer 前缀 0xff")

    def lenenc_bytes(self) -> bytes | None:
        length = self.lenenc()
        if length is None:
            return None
        return self.take(length)

    def nul_string(self) -> bytes:
        end = self.data.find(b"\x00", self.pos)
        if end < 0:
            raise _protocol_error("缺少 NUL 结尾的字符串")
        value = self.data[self.pos : end]
        self.pos = end + 1
        return value

    def rest(self) -> bytes:
        value = self.data[self.pos :]
        self.pos = len(self.data)
        return value


def _protocol_error(message: str) -> MySQLDatabaseError:
    return MySQLDatabaseError(f"MySQL 协议错误: {message}")


def _decode_text(raw: bytes) -> str:
    return raw.decode("utf-8")


def _scramble_native_password(password: str, seed: bytes) -> bytes:
    """mysql_native_password: SHA1(pw) XOR SHA1(seed + SHA1(SHA1(pw)))。"""
    if not password:
        return b""
    stage1 = hashlib.sha1(password.encode("utf-8")).digest()
    stage2 = hashlib.sha1(stage1).digest()
    digest = hashlib.sha1(seed[:20] + stage2).digest()
    return bytes(a ^ b for a, b in zip(stage1, digest))


class _Column:
    __slots__ = ("name", "type_code", "charset", "flags")

    def __init__(self, name: str, type_code: int, charset: int, flags: int) -> None:
        self.name = name
        self.type_code = type_code
        self.charset = charset
        self.flags = flags


def _parse_column(packet: bytes) -> _Column:
    reader = _Reader(packet)
    reader.lenenc_bytes()  # catalog ("def")
    reader.lenenc_bytes()  # schema
    reader.lenenc_bytes()  # table
    reader.lenenc_bytes()  # org_table
    name = reader.lenenc_bytes() or b""
    reader.lenenc_bytes()  # org_name
    reader.lenenc()  # fixed-length fields 长度，固定 0x0c
    charset = reader.uint16()
    reader.uint32()  # column length
    type_code = reader.byte()
    flags = reader.uint16()
    reader.byte()  # decimals
    reader.take(2)  # filler
    return _Column(name.decode("utf-8", "replace"), type_code, charset, flags)


def _decode_value(raw: bytes, column: _Column) -> Any:
    if column.type_code in _INTEGER_TYPES:
        return int(raw)
    if column.type_code in _FLOAT_TYPES or column.type_code in _DECIMAL_TYPES:
        return float(raw)
    return _decode_text(raw)


def _parse_row(packet: bytes, columns: Sequence[_Column]) -> dict:
    reader = _Reader(packet)
    row: dict[str, Any] = {}
    for column in columns:
        raw = reader.lenenc_bytes()
        row[column.name] = None if raw is None else _decode_value(raw, column)
    return row


def _is_eof(packet: bytes) -> bool:
    return bool(packet) and packet[0] == 0xFE and len(packet) < 9


def _parse_ok(packet: bytes) -> tuple[int, int, int]:
    reader = _Reader(packet)
    reader.byte()  # 0x00 / 0xfe
    affected_rows = reader.lenenc() or 0
    last_insert_id = reader.lenenc() or 0
    status = 0
    if not reader.eof():
        status = reader.uint16()
        reader.uint16()  # warnings
    return affected_rows, last_insert_id, status


def _raise_server_error(packet: bytes) -> None:
    reader = _Reader(packet)
    reader.byte()  # 0xff
    errno = reader.uint16()
    sqlstate: str | None = None
    if not reader.eof() and reader.peek_byte() == 0x23:  # '#'
        reader.byte()
        sqlstate = reader.take(5).decode("ascii", "replace")
    message = reader.rest().decode("utf-8", "replace")
    raise MySQLDatabaseError(
        f"MySQL error {errno}: {message}", errno=errno, sqlstate=sqlstate
    )


# ------------------------------------------------------------------ 参数转义

_ESCAPE_TABLE = str.maketrans(
    {
        "\\": "\\\\",
        "'": "\\'",
        '"': '\\"',
        "\x00": "\\0",
        "\n": "\\n",
        "\r": "\\r",
        "\x1a": "\\Z",
        "\b": "\\b",
        "\t": "\\t",
    }
)


def _quote_string(value: str) -> str:
    return "'" + value.translate(_ESCAPE_TABLE) + "'"


def _format_param(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("MySQL 参数不能是 NaN/Infinity")
        return repr(value)
    if isinstance(value, str):
        return _quote_string(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "X'" + bytes(value).hex() + "'"
    raise TypeError(f"不支持的 MySQL 参数类型: {type(value).__name__}")


def _skip_quoted(sql: str, start: int) -> int:
    """返回引号片段结束后的下标；支持反斜杠与双写引号两种转义。"""
    quote = sql[start]
    i = start + 1
    n = len(sql)
    while i < n:
        char = sql[i]
        if char == "\\" and quote in ("'", '"'):
            i += 2
            continue
        if char == quote:
            if i + 1 < n and sql[i + 1] == quote:
                i += 2
                continue
            return i + 1
        i += 1
    raise ValueError("SQL 中存在未闭合的引号")


def _skip_comment(sql: str, start: int) -> int | None:
    """如果 start 处是注释，返回注释后的下标，否则返回 None。"""
    n = len(sql)
    if sql.startswith("--", start) and (
        start + 2 >= n or sql[start + 2].isspace()
    ):
        end = sql.find("\n", start + 2)
        return n if end < 0 else end
    if sql[start] == "#":
        end = sql.find("\n", start + 1)
        return n if end < 0 else end
    if sql.startswith("/*", start):
        end = sql.find("*/", start + 2)
        return n if end < 0 else end + 2
    return None


def _substitute_params(sql: str, params: Sequence[Any]) -> str:
    """把字符串/注释之外的 ``?`` 替换为转义后的字面量，并校验占位符数量。"""
    out: list[str] = []
    index = 0
    count = 0
    n = len(sql)
    while index < n:
        char = sql[index]
        if char in ("'", '"', "`"):
            end = _skip_quoted(sql, index)
            out.append(sql[index:end])
            index = end
            continue
        comment_end = _skip_comment(sql, index)
        if comment_end is not None:
            out.append(sql[index:comment_end])
            index = comment_end
            continue
        if char == "?":
            if count >= len(params):
                raise ValueError(
                    f"SQL 占位符数量多于参数数量: {len(params)} 个参数"
                )
            out.append(_format_param(params[count]))
            count += 1
            index += 1
            continue
        out.append(char)
        index += 1
    if count != len(params):
        raise ValueError(
            f"SQL 占位符数量与参数数量不一致: {count} 个占位符，{len(params)} 个参数"
        )
    return "".join(out)


def _split_script(script: str) -> list[str]:
    """按语句外的 ``;`` 拆分脚本，保留引号与注释中的分号。"""
    statements: list[str] = []
    start = 0
    index = 0
    n = len(script)
    while index < n:
        char = script[index]
        if char in ("'", '"', "`"):
            index = _skip_quoted(script, index)
            continue
        comment_end = _skip_comment(script, index)
        if comment_end is not None:
            index = comment_end
            continue
        if char == ";":
            chunk = script[start:index].strip()
            if _has_sql(chunk):
                statements.append(chunk)
            start = index + 1
        index += 1
    chunk = script[start:].strip()
    if _has_sql(chunk):
        statements.append(chunk)
    return statements


def _has_sql(chunk: str) -> bool:
    """chunk 去掉空白与注释后是否还有可执行 SQL。"""
    index = 0
    n = len(chunk)
    while index < n:
        if chunk[index].isspace():
            index += 1
            continue
        comment_end = _skip_comment(chunk, index)
        if comment_end is not None:
            index = comment_end
            continue
        return True
    return False


class MySQLCursor:
    """文本协议结果游标；结果已在 execute 时全部读入。"""

    rowcount: int

    def __init__(
        self,
        rows: list[dict],
        rowcount: int,
        columns: Sequence[_Column] = (),
    ) -> None:
        self._rows = rows
        self._columns = list(columns)
        self._index = 0
        self._closed = False
        self.rowcount = rowcount

    def fetchone(self) -> dict | None:
        if self._closed:
            raise MySQLDatabaseError("游标已关闭")
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    def fetchall(self) -> list[dict]:
        if self._closed:
            raise MySQLDatabaseError("游标已关闭")
        rows = self._rows[self._index :]
        self._index = len(self._rows)
        return list(rows)

    def close(self) -> None:
        self._closed = True
        self._rows = []
        self._index = 0


class MySQLConnection:
    """单个 MySQL/MariaDB 连接；非线程安全，多线程请各自 connect。"""

    def __init__(self, sock: socket.socket, target: _Target) -> None:
        self._sock = sock
        self._target = target
        self._seq = 0
        self._closed = False
        self.server_version = ""
        self.connection_id: int | None = None

    # -------------------------------------------------------------- 启动

    def _startup(self) -> None:
        greeting = self._read_packet()
        if not greeting:
            raise _protocol_error("服务器握手包为空")
        if greeting[0] == 0xFF:
            _raise_server_error(greeting)
        if greeting[0] != 10:
            raise _protocol_error(
                f"不支持的握手协议版本 {greeting[0]}（只支持 v10）"
            )
        seed, plugin = self._parse_handshake(greeting)
        token = _scramble_native_password(self._target.password, seed)
        self._send_handshake_response(token)
        self._finish_authentication(seed, plugin)
        # 连接级会话设置：显式 utf8mb4 + 关自动提交，让 commit/rollback 生效。
        self.execute("SET NAMES utf8mb4").close()
        self.execute("SET SESSION autocommit=0").close()

    def _parse_handshake(self, packet: bytes) -> tuple[bytes, str]:
        reader = _Reader(packet)
        reader.byte()  # protocol version
        self.server_version = reader.nul_string().decode("utf-8", "replace")
        self.connection_id = reader.uint32()
        seed1 = reader.take(8)
        reader.byte()  # filler
        capabilities = reader.uint16()
        if reader.eof():
            raise _protocol_error("服务器握手包缺少协议 4.1 字段")
        reader.byte()  # character set
        reader.uint16()  # status flags
        capabilities |= reader.uint16() << 16
        auth_data_length = reader.byte()
        reader.take(10)  # reserved
        if capabilities & _CLIENT_PLUGIN_AUTH:
            part2_length = max(13, auth_data_length - 8)
        else:
            part2_length = 12
        seed2 = reader.take(min(part2_length, reader.remaining))
        plugin = ""
        if capabilities & _CLIENT_PLUGIN_AUTH and not reader.eof():
            plugin = reader.nul_string().decode("ascii", "replace")
        if not capabilities & _CLIENT_PROTOCOL_41:
            raise _protocol_error("服务器不支持 CLIENT_PROTOCOL_41")
        if not capabilities & _CLIENT_SECURE_CONNECTION:
            raise _protocol_error("服务器不支持 CLIENT_SECURE_CONNECTION")
        if not capabilities & _CLIENT_PLUGIN_AUTH:
            raise _protocol_error("服务器不支持 CLIENT_PLUGIN_AUTH")
        self._server_capabilities = capabilities
        return (seed1 + seed2)[:20], plugin

    def _send_handshake_response(self, token: bytes) -> None:
        if self._target.database and not (
            self._server_capabilities & _CLIENT_CONNECT_WITH_DB
        ):
            raise _protocol_error("服务器不支持 CLIENT_CONNECT_WITH_DB")
        capabilities = _CLIENT_BASE_CAPABILITIES
        if self._target.database:
            capabilities |= _CLIENT_CONNECT_WITH_DB
        capabilities &= self._server_capabilities
        payload = bytearray()
        payload += struct.pack("<I", capabilities)
        payload += struct.pack("<I", 16 * 1024 * 1024)
        payload.append(_CLIENT_CHARSET_UTF8MB4)
        payload += b"\x00" * 23
        payload += self._target.user.encode("utf-8") + b"\x00"
        payload.append(len(token))
        payload += token
        if self._target.database:
            payload += self._target.database.encode("utf-8") + b"\x00"
        payload += _MYSQL_NATIVE_PASSWORD.encode("ascii") + b"\x00"
        self._write_packet(bytes(payload))

    def _finish_authentication(self, seed: bytes, plugin: str) -> None:
        while True:
            packet = self._read_packet()
            if not packet:
                raise _protocol_error("认证阶段连接被服务器关闭")
            header = packet[0]
            if header == 0x00:
                _parse_ok(packet)
                return
            if header == 0xFF:
                _raise_server_error(packet)
            if header == 0xFE:
                seed, plugin = self._handle_auth_switch(packet)
                token = self._auth_token(seed, plugin)
                self._write_packet(token)
                continue
            if header == 0x01:
                raise MySQLDatabaseError(
                    f"认证插件 {plugin or '未知'} 需要额外的 AuthMoreData，暂不支持"
                )
            raise _protocol_error(f"认证阶段收到未知包头 0x{header:02x}")

    def _handle_auth_switch(self, packet: bytes) -> tuple[bytes, str]:
        reader = _Reader(packet)
        reader.byte()  # 0xfe
        if reader.eof():
            raise MySQLDatabaseError("服务器要求旧式密码认证（不支持）")
        plugin = reader.nul_string().decode("ascii", "replace")
        seed = reader.rest()
        if not plugin:
            # 旧式 AuthSwitchRequest 只有 scramble，没有插件名。
            plugin = _MYSQL_NATIVE_PASSWORD
        return seed[:20], plugin

    def _auth_token(self, seed: bytes, plugin: str) -> bytes:
        if plugin and plugin != _MYSQL_NATIVE_PASSWORD:
            raise MySQLDatabaseError(
                f"不支持的认证插件: {plugin}（只支持 {_MYSQL_NATIVE_PASSWORD}）"
            )
        return _scramble_native_password(self._target.password, seed)

    # -------------------------------------------------------------- 包收发

    def _recv_exact(self, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0:
            try:
                chunk = self._sock.recv(remaining)
            except socket.timeout as exc:
                raise MySQLDatabaseError("MySQL 读超时") from exc
            except OSError as exc:
                raise MySQLDatabaseError(f"MySQL 读取失败: {exc}") from exc
            if not chunk:
                raise MySQLDatabaseError("MySQL 连接被服务器关闭")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _read_packet(self) -> bytes:
        header = self._recv_exact(4)
        length = header[0] | (header[1] << 8) | (header[2] << 16)
        sequence = header[3]
        if sequence != self._seq:
            raise _protocol_error(
                f"包序号不匹配: 期望 {self._seq}，实际 {sequence}"
            )
        self._seq = (self._seq + 1) & 0xFF
        payload = self._recv_exact(length)
        while length == _MAX_PACKET:
            header = self._recv_exact(4)
            length = header[0] | (header[1] << 8) | (header[2] << 16)
            sequence = header[3]
            if sequence != self._seq:
                raise _protocol_error(
                    f"包序号不匹配: 期望 {self._seq}，实际 {sequence}"
                )
            self._seq = (self._seq + 1) & 0xFF
            payload += self._recv_exact(length)
        return payload

    def _write_packet(self, payload: bytes) -> None:
        offset = 0
        while True:
            chunk = payload[offset : offset + _MAX_PACKET]
            header = bytes(
                (
                    len(chunk) & 0xFF,
                    (len(chunk) >> 8) & 0xFF,
                    (len(chunk) >> 16) & 0xFF,
                    self._seq,
                )
            )
            try:
                self._sock.sendall(header + chunk)
            except socket.timeout as exc:
                raise MySQLDatabaseError("MySQL 写超时") from exc
            except OSError as exc:
                raise MySQLDatabaseError(f"MySQL 写入失败: {exc}") from exc
            self._seq = (self._seq + 1) & 0xFF
            offset += len(chunk)
            if len(chunk) < _MAX_PACKET:
                return

    def _command(self, payload: bytes) -> None:
        if self._closed:
            raise MySQLDatabaseError("MySQL 连接已关闭")
        self._seq = 0
        self._write_packet(payload)

    # -------------------------------------------------------------- 查询

    def execute(self, sql: str, params: tuple = ()) -> MySQLCursor:
        """执行一条语句；参数占位符为 ``?``，返回已读完结果的游标。"""
        if not isinstance(sql, str):
            raise TypeError("SQL 必须是 str")
        if params:
            sql = _substitute_params(sql, tuple(params))
        self._command(b"\x03" + sql.encode("utf-8"))
        return self._read_result()

    def executescript(self, script: str) -> None:
        """按 ``;`` 拆分脚本逐条执行；不自动 commit。"""
        if not isinstance(script, str):
            raise TypeError("SQL 脚本必须是 str")
        for statement in _split_script(script):
            self.execute(statement).close()

    def commit(self) -> None:
        self.execute("COMMIT").close()

    def rollback(self) -> None:
        self.execute("ROLLBACK").close()

    def close(self) -> None:
        """发 COM_QUIT 并关闭 socket；重复调用与网络错误都容错。"""
        if self._closed:
            return
        try:
            self._seq = 0
            self._write_packet(b"\x01")
        except (MySQLDatabaseError, OSError):
            pass
        self._closed = True
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass

    def __enter__(self) -> "MySQLConnection":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def _read_result(self) -> MySQLCursor:
        packet = self._read_packet()
        if not packet:
            raise _protocol_error("查询响应为空")
        header = packet[0]
        if header == 0xFF:
            _raise_server_error(packet)
        if header == 0x00:
            affected_rows, _last_insert_id, _status = _parse_ok(packet)
            return MySQLCursor([], affected_rows)
        if header == 0xFB:
            self._abort_local_infile()
            raise MySQLDatabaseError("不支持 LOAD DATA LOCAL INFILE")
        reader = _Reader(packet)
        column_count = reader.lenenc()
        if not column_count:
            raise _protocol_error("结果集列数为 0")
        columns = []
        for _ in range(column_count):
            column_packet = self._read_packet()
            if column_packet and column_packet[0] == 0xFF:
                _raise_server_error(column_packet)
            columns.append(_parse_column(column_packet))
        terminator = self._read_packet()
        if not _is_eof(terminator):
            raise _protocol_error("列定义后缺少 EOF 包")
        rows: list[dict] = []
        while True:
            row_packet = self._read_packet()
            if not row_packet:
                raise _protocol_error("结果集在 EOF 前结束")
            if _is_eof(row_packet):
                break
            if row_packet[0] == 0xFF:
                _raise_server_error(row_packet)
            rows.append(_parse_row(row_packet, columns))
        return MySQLCursor(rows, len(rows), columns)

    def _abort_local_infile(self) -> None:
        """拒绝 LOAD DATA LOCAL INFILE 时发送空包，让服务器结束该请求。"""
        try:
            self._write_packet(b"")
            response = self._read_packet()
            if response and response[0] == 0xFF:
                return
        except MySQLDatabaseError:
            pass
