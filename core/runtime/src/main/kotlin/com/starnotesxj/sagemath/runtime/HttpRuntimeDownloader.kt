package com.starnotesxj.sagemath.runtime

import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.file.Files
import java.nio.file.Path
import java.time.Duration

/**
 * JDK-only HTTPS downloader used by the product adapter. Redirects remain
 * limited to normal HTTP redirects; the artifact URI itself must be HTTPS.
 */
class JdkHttpRuntimeDownloader(
    private val requestTimeout: Duration = DEFAULT_REQUEST_TIMEOUT,
    private val maxDownloadBytes: Long = HttpRuntimeDownloader.DEFAULT_MAX_DOWNLOAD_BYTES,
) : RuntimeDownloader {
    private val client: HttpClient = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .connectTimeout(DEFAULT_CONNECT_TIMEOUT)
        .build()
    override fun download(
        artifact: RuntimeArtifact,
        destination: java.nio.file.Path,
        progress: DownloadProgressListener,
        cancellation: InstallationCancellation,
    ): DownloadedArtifact {
        require(artifact.uri.scheme.equals("https", ignoreCase = true)) {
            "Managed SageMath downloads must use HTTPS"
        }
        require(!requestTimeout.isZero && !requestTimeout.isNegative) { "HTTP request timeout must be positive" }
        require(maxDownloadBytes > 0) { "Maximum download size must be positive" }
        ensureDownloadPathIsSafe(destination)
        val request = HttpRequest.newBuilder(artifact.uri)
            .timeout(requestTimeout)
            .header("Accept", "application/octet-stream")
            .GET()
            .build()
        val response = try {
            client.send(request, HttpResponse.BodyHandlers.ofInputStream())
        }
        catch (error: Exception) {
            Files.deleteIfExists(destination)
            throw RuntimeInstallException("DOWNLOAD_HTTP", "Unable to download the SageMath runtime", error)
        }
        response.body().use { body ->
            if (
                !response.uri().scheme.equals("https", ignoreCase = true) ||
                !response.uri().host.equals(artifact.uri.host, ignoreCase = true)
            ) {
                Files.deleteIfExists(destination)
                throw RuntimeInstallException("DOWNLOAD_REDIRECT_INSECURE", "Runtime download redirected outside the HTTPS artifact host")
            }
            if (response.statusCode() !in 200..299) {
                Files.deleteIfExists(destination)
                throw RuntimeInstallException(
                    "DOWNLOAD_HTTP_STATUS",
                    "SageMath runtime download returned HTTP ${response.statusCode()}",
                )
            }
            val contentLength = response.headers()
                .firstValueAsLong("Content-Length")
                .orElse(-1L)
            if (artifact.sizeBytes != null && contentLength >= 0 && contentLength != artifact.sizeBytes) {
                Files.deleteIfExists(destination)
                throw RuntimeInstallException("DOWNLOAD_SIZE_MISMATCH", "HTTP content length does not match the catalog")
            }
            return try {
                copyAndVerify(
                    artifact,
                    body,
                    destination,
                    progress,
                    cancellation,
                    maxDownloadBytes,
                )
            }
            catch (error: Exception) {
                Files.deleteIfExists(destination)
                throw error
            }
        }
    }

    companion object {
        private val DEFAULT_CONNECT_TIMEOUT: Duration = Duration.ofSeconds(30)
        private val DEFAULT_REQUEST_TIMEOUT: Duration = Duration.ofMinutes(30)

        private fun copyAndVerify(
            artifact: RuntimeArtifact,
            input: java.io.InputStream,
            destination: java.nio.file.Path,
            progress: DownloadProgressListener,
            cancellation: InstallationCancellation,
            maxDownloadBytes: Long,
        ): DownloadedArtifact = HttpRuntimeDownloader(
            connectionFactory = { input },
            maxDownloadBytes = maxDownloadBytes,
        ).download(artifact, destination, progress, cancellation)
    }
}
