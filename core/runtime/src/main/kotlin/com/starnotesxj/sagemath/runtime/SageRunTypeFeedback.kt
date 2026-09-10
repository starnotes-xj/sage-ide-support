package com.starnotesxj.sagemath.runtime

import java.nio.charset.StandardCharsets
import java.util.Base64

/** Concrete types collected from one normal Sage script execution. */
data class SageRunTypeFeedback(
    val runId: String,
    val sourceDigest: String,
    val observedTypes: Map<String, SageObservedType>,
)

/**
 * Protocol for the private sidecar produced by an opt-in normal Sage run.
 *
 * The bootstrap is loaded through ``sitecustomize`` and wraps only Sage's own
 * RunFileCmd entry point.  It executes the user script through the original
 * implementation, then writes the types of user-created/changed globals to a
 * temporary sidecar.  It never writes protocol lines to the user's console.
 */
object SageRunTypeFeedbackProtocol {
    const val MAGIC = "__SAGE_IDE_RUN_TYPE_FEEDBACK__"
    const val BOOTSTRAP_PATH_ENV = "SAGE_IDE_RUN_TYPE_BOOTSTRAP"
    const val OUTPUT_PATH_ENV = "SAGE_IDE_RUN_TYPE_FEEDBACK_FILE"
    const val RUN_ID_ENV = "SAGE_IDE_RUN_TYPE_FEEDBACK_ID"
    const val SOURCE_DIGEST_ENV = "SAGE_IDE_RUN_TYPE_SOURCE_DIGEST"
    const val MAX_SIDECAR_BYTES = 128 * 1024

    fun decode(
        line: String,
        expectedRunId: String,
        expectedSourceDigest: String,
    ): SageRunTypeFeedback? {
        val parts = line.trimEnd('\r', '\n').split('\t', limit = 4)
        if (parts.size != 4 || parts[0] != MAGIC || parts[1] != expectedRunId || parts[2] != expectedSourceDigest) {
            return null
        }
        val payload = decodeBase64(parts[3]) ?: return null
        return SageRunTypeFeedback(expectedRunId, expectedSourceDigest, decodeRecords(payload))
    }

    private fun decodeRecords(payload: String): Map<String, SageObservedType> = buildMap {
        payload.split(RECORD_SEPARATOR).forEach { record ->
            val fields = record.split('|', limit = 3)
            if (fields.size != 3 || !fields[0].matches(IDENTIFIER)) return@forEach
            val runtime = decodeBase64(fields[1]) ?: return@forEach
            val mro = decodeBase64(fields[2])?.split(MRO_SEPARATOR)?.filter(String::isNotBlank).orEmpty()
            if (runtime.isNotBlank() && mro.isNotEmpty()) put(fields[0], SageObservedType(runtime, mro))
        }
    }

    private fun decodeBase64(value: String): String? = runCatching {
        String(Base64.getDecoder().decode(value), StandardCharsets.UTF_8)
    }.getOrNull()

    private val IDENTIFIER = Regex("[A-Za-z_][A-Za-z0-9_]*")
    private const val RECORD_SEPARATOR = "\u001e"
    private const val MRO_SEPARATOR = "\u001f"

    /** Fixed Python bootstrap; all per-run data arrives through environment variables. */
    val SITE_CUSTOMIZE_SOURCE = """
        import base64
        import os
        import re
        import tempfile

        _magic = '$MAGIC'
        _output_path = os.environ.get('$OUTPUT_PATH_ENV')
        _run_id = os.environ.get('$RUN_ID_ENV')
        _source_digest = os.environ.get('$SOURCE_DIGEST_ENV')
        _identifier = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
        _record_separator = '\x1e'
        _mro_separator = '\x1f'
        _max_bytes = $MAX_SIDECAR_BYTES
        # Base64 expands the record payload.  Reserve room for the line header
        # and keep the final sidecar below the host parser's hard limit.
        _record_limit = int(_max_bytes * 0.70)

        def _encode(value):
            return base64.b64encode(value.encode('utf-8')).decode('ascii')

        def _write_feedback(namespace, baseline):
            if not (_output_path and _run_id and _source_digest and namespace is not None):
                return
            records = []
            used = 0
            for name in sorted(namespace):
                if not _identifier.match(name):
                    continue
                value = namespace[name]
                if name in baseline and baseline[name] is value:
                    continue
                value_class = type(value)
                runtime = '%s.%s' % (value_class.__module__, value_class.__qualname__)
                mro = _mro_separator.join('%s.%s' % (base.__module__, base.__qualname__) for base in value_class.__mro__)
                record = name + '|' + _encode(runtime) + '|' + _encode(mro)
                added = len(record.encode('utf-8')) + (1 if records else 0)
                if used + added > _record_limit:
                    break
                records.append(record)
                used += added
            payload = _encode(_record_separator.join(records))
            line = _magic + '\t' + _run_id + '\t' + _source_digest + '\t' + payload + '\n'
            directory = os.path.dirname(_output_path) or '.'
            fd, temporary = tempfile.mkstemp(prefix='.sage-ide-feedback-', dir=directory)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8', newline='') as output:
                    output.write(line)
                os.replace(temporary, _output_path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

        try:
            import sage.cli.run_file_cmd as _run_file_cmd
            _original_run = _run_file_cmd.RunFileCmd.run
            _original_sage_globals = _run_file_cmd.sage_globals
            _captured = {'namespace': None, 'baseline': {}}

            def _sage_globals_with_capture():
                namespace = _original_sage_globals()
                _captured['namespace'] = namespace
                _captured['baseline'] = dict(namespace)
                return namespace

            def _run_with_feedback(self):
                try:
                    return _original_run(self)
                finally:
                    try:
                        _write_feedback(_captured['namespace'], _captured['baseline'])
                    except Exception:
                        pass

            _run_file_cmd.sage_globals = _sage_globals_with_capture
            _run_file_cmd.RunFileCmd.run = _run_with_feedback
        except Exception:
            pass
    """.trimIndent()
}
