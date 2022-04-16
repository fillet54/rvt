
CodeMirror.defineSimpleMode("rvt", {
    // The start state contains the rules that are initially used
    start: [
        { regex: /(?:[a-zA-Z_][a-zA-Z0-9_]*)/, token: "keyword", sol: true },
    ],
});
