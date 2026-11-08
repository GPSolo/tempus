package com.eddyizm.tempus.service;

import static org.junit.Assert.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import androidx.media3.common.C;
import androidx.media3.common.Player;

import org.junit.Before;
import org.junit.Test;

import java.lang.reflect.Method;

public class MediaManagerPlayNextOrderTest {
    private Player player;
    private Method insertPosition;
    private Method reset;

    @Before
    public void setUp() throws Exception {
        player = mock(Player.class);
        insertPosition = MediaManager.class.getDeclaredMethod("computePlayNextInsertPos", Player.class, int.class, boolean.class);
        insertPosition.setAccessible(true);
        reset = MediaManager.class.getDeclaredMethod("resetPlayNextBlock");
        reset.setAccessible(true);
        reset.invoke(null);
    }

    private int insert(int count, boolean preserveOrder) throws Exception {
        return (int) insertPosition.invoke(null, player, count, preserveOrder);
    }

    @Test
    public void explicitBatchesAppendAfterExistingBlock() throws Exception {
        when(player.getCurrentMediaItemIndex()).thenReturn(1);
        assertEquals(2, insert(2, true));
        assertEquals(4, insert(1, true));
        assertEquals(5, insert(3, true));
    }

    @Test
    public void disabledPreservationKeepsStockInsertion() throws Exception {
        when(player.getCurrentMediaItemIndex()).thenReturn(1);
        assertEquals(2, insert(2, false));
        assertEquals(2, insert(1, false));
    }

    @Test
    public void currentTrackChangeReanchorsBlock() throws Exception {
        when(player.getCurrentMediaItemIndex()).thenReturn(1);
        assertEquals(2, insert(3, true));
        when(player.getCurrentMediaItemIndex()).thenReturn(2);
        assertEquals(3, insert(1, true));
        assertEquals(4, insert(1, true));
    }

    @Test
    public void manualEditResetsBlock() throws Exception {
        when(player.getCurrentMediaItemIndex()).thenReturn(1);
        assertEquals(2, insert(3, true));
        reset.invoke(null);
        assertEquals(2, insert(1, true));
    }

    @Test
    public void unsetCurrentTrackClearsBlock() throws Exception {
        when(player.getCurrentMediaItemIndex()).thenReturn(1);
        assertEquals(2, insert(3, true));
        when(player.getCurrentMediaItemIndex()).thenReturn(C.INDEX_UNSET);
        assertEquals(0, insert(1, true));
        when(player.getCurrentMediaItemIndex()).thenReturn(1);
        assertEquals(2, insert(1, true));
    }
}
