package com.berat.legaltech.gateway.exception;

public class PythonServiceException extends RuntimeException {
    private final int statusCode;

    public PythonServiceException(int statusCode, String message) {
        super(message);
        this.statusCode = statusCode;
    }

    public int getStatusCode() {
        return statusCode;
    }
}
