package com.aboubakr.wallet;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;

import java.io.File;
import java.io.FileNotFoundException;

/**
 * Gives the camera app one file to write the receipt photo into, and lets the
 * WebView read it back. Nothing else is shared.
 */
public class PhotoProvider extends ContentProvider {
    static final String AUTHORITY = "com.aboubakr.wallet.photos";
    static final Uri CAPTURE_URI = Uri.parse("content://" + AUTHORITY + "/capture.jpg");

    static File captureFile(Context c) {
        return new File(c.getCacheDir(), "capture.jpg");
    }

    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public String getType(Uri uri) {
        return "image/jpeg";
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (!"capture.jpg".equals(uri.getLastPathSegment())) throw new FileNotFoundException(uri.toString());
        int flags = mode.contains("w")
                ? ParcelFileDescriptor.MODE_READ_WRITE | ParcelFileDescriptor.MODE_CREATE | ParcelFileDescriptor.MODE_TRUNCATE
                : ParcelFileDescriptor.MODE_READ_ONLY;
        return ParcelFileDescriptor.open(captureFile(getContext()), flags);
    }

    @Override
    public Cursor query(Uri uri, String[] projection, String selection, String[] args, String sort) {
        MatrixCursor c = new MatrixCursor(new String[]{"_display_name", "_size"});
        c.addRow(new Object[]{"receipt.jpg", captureFile(getContext()).length()});
        return c;
    }

    @Override
    public Uri insert(Uri uri, ContentValues values) {
        return null;
    }

    @Override
    public int delete(Uri uri, String selection, String[] args) {
        return 0;
    }

    @Override
    public int update(Uri uri, ContentValues values, String selection, String[] args) {
        return 0;
    }
}
